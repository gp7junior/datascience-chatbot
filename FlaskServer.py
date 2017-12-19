from threading import Lock
from flask import g, Flask, render_template, session, flash, redirect, request, send_from_directory, url_for
from flask_socketio import SocketIO, emit, disconnect
from werkzeug import secure_filename

import requests
import os.path
import sys
import json
import pandas as pd
import io

# import my_chatbot as mcb

try:
    import apiai
except ImportError:
    sys.path.append(
        os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir)
    )

# Set this variable to "threading", "eventlet" or "gevent" to test the
async_mode = 'threading'

# Token for acces the Chatbot on DialogFlow
CLIENT_ACCESS_TOKEN = 'your client token'
DEVELOPER_ACCESS_TOKEN = 'your developer token'

# UPLOAD_FOLDER = '/Users/gp7junior/Code/DScience Chatbot V1/'
ALLOWED_EXTENSIONS = set(['csv', 'xls'])

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
# app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
socketio = SocketIO(app, async_mode=async_mode)
# socketio = SocketIO(app)
thread = None
thread_lock = Lock()

# Defining the session variables


#session['command_history'].append("beginning of the pyhon commands used")


def speak_json(message):
    ai = apiai.ApiAI(CLIENT_ACCESS_TOKEN)
    request = ai.text_request()
    request.session_id = "001"
    request.query = message
    response = request.getresponse()
    parsed = json.loads(response.read())
    return (parsed)


def sending_entities(feature_name, values):
    data = {}
    data['name'] = feature_name
    data['entries'] = []
    for value in values:
        data['entries'].append({'value': value})
    data = json.dumps(data)
    # 1 DEFINE THE URL
    url = 'https://api.dialogflow.com/v1/entities?v=20150910'
    # 2 DEFINE THE HEADERS
    headers = {'Authorization': 'Bearer ' + DEVELOPER_ACCESS_TOKEN, 'Content-Type': 'application/json'}
    # 3 MAKE THE REQUEST
    response = requests.post(url, headers=headers, data=data)
    print(response.json)


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Begining of FLask functions:
def background_thread(session):
    """Example of how to send server generated events to clients."""
    count = 0
    old_size = len(session['command_history'])
    while True:
        socketio.sleep(10)
        if old_size < len(session['command_history']):
            socketio.emit('bot_command_line_response', {'data': session['command_history'][-1]},namespace='/test')
            old_size = len(session['command_history'])
        #socketio.emit('bot_request',
        #              {'data': 'Server generated event', 'count': count},
        #              namespace='/test')


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'],
                               filename)


@app.route('/', methods=['GET', 'POST'])
def index():
    return render_template('index.html', async_mode=socketio.async_mode)

@app.before_first_request
def _run_on_start():
    command_history = ["beginning of the pyhon commands used"]
    session['command_history'] = command_history


@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    print('I am at upload file')
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        # if user does not select file, browser also submit a empty part without filename
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            session['filename'] = secure_filename(file.filename)
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_input = pd.read_csv(stream, sep=None, engine='python')
            print(csv_input.describe())
            # file.save(os.path.join(session['filename']))
            csv_input.to_csv(session['filename'], sep=',')
            session['receive_count'] = session.get('receive_count', 0) + 1
            command_used = 'ooook'
            session['command_history'].append(command_used)
            feature_list = csv_input.columns.get_values()
            sending_entities(feature_name='Features', values=feature_list.tolist())
            # return redirect(url_for('uploaded_file',filename=filename))
            # classify_data()
            for column in csv_input:
                values = csv_input[column].unique().tolist()
                sending_entities(feature_name=column.replace(" ", "_").lower(), values=values)
            return redirect(url_for('index'))
    return redirect(url_for('index'))


# this function uses a DialogFlow call and send the response via a socket to the client
@socketio.on('say_welcome', namespace='/test')
def say_welcome():
    ai = apiai.ApiAI(CLIENT_ACCESS_TOKEN)
    request = ai.event_request(apiai.events.Event("welcome"))
    response = request.getresponse()
    parsed = json.loads(response.read())
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('bot_response',
         {'data': parsed['result']['fulfillment']['speech'], 'count': session['receive_count']})
    emit('bot_request',
         {'data': 'User asked for a hifive', 'count': session['receive_count']})


def emit_to_command_line(command):
    emit('bot_command_line_response',
         dict(data=command, count=session['receive_count']))


def basic_description():
    csv_input = pd.read_csv(session['filename'], sep=None)
    # print(csv_input)
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('bot_command_line_response', {'data': '<your_file>.describe', 'count': session['receive_count']})
    result = csv_input.describe()
    return (type(result))

@socketio.on('connect', namespace='/test')
def test_connect():
    global thread
    with thread_lock:
        if thread is None:
            thread = socketio.start_background_task(target=background_thread, session=session._get_current_object())
    emit('my_response', {'data': 'Connected', 'count': 0})


@socketio.on('send_message', namespace='/test')
def send_message(message):

    old_size = len(session['command_history'])

    bot_response = speak_json(message['data'])
    bot_speech = bot_response['result']['fulfillment']['speech']
    actual_intent = bot_response['result']['metadata']['intentName']
    #actual_result = bot_response['result']

    session['receive_count'] = session.get('receive_count', 0) + 1

    # Intent identification and programming logic
    if actual_intent == 'upload_data':
        emit('upload_file_response')
        command_used = "csv_input = pd.read_csv('<your_file_name>',sep=None,engine='python')"
        session['command_history'].append(command_used)
    #if old_size < len(session['command_history']):
    #    emit('bot_command_line_response', {'data': session['command_history'][-1]})

    emit('bot_response',{'data': bot_speech, 'intent':actual_intent})
    emit('bot_request' ,{'data': message['data']})

if __name__ == '__main__':
    socketio.run(app, debug=True, use_debugger=False, use_reloader=False)
