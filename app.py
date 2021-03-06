# -*- coding: utf-8 -*-

import flask
import mwapi
import mwoauth
import os
import random
import requests_oauthlib
import string
import toolforge
import yaml
import json
import mwparserfromhell

app = flask.Flask(__name__)

user_agent = toolforge.set_user_agent('musikverket-description-translations', email='tools.musikverket-description-translations@tools.wmflabs.org')
target_instance = 'https://commons.wikimedia.org/w/index.php'

__dir__ = os.path.dirname(__file__)
try:
    with open(os.path.join(__dir__, 'config.yaml')) as config_file:
        app.config.update(yaml.safe_load(config_file))
except FileNotFoundError:
    print('config.yaml file not found, assuming local development setup')
    app.secret_key = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(64))

if 'oauth' in app.config:
    consumer_token = mwoauth.ConsumerToken(app.config['oauth']['consumer_key'], app.config['oauth']['consumer_secret'])


@app.template_global()
def csrf_token():
    if 'csrf_token' not in flask.session:
        flask.session['csrf_token'] = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(64))
    return flask.session['csrf_token']

@app.template_global()
def form_value(name):
    if 'repeat_form' in flask.g and name in flask.request.form:
        return (flask.Markup(r' value="') +
                flask.Markup.escape(flask.request.form[name]) +
                flask.Markup(r'" '))
    else:
        return flask.Markup()

@app.template_global()
def form_attributes(name):
    return (flask.Markup(r' id="') +
            flask.Markup.escape(name) +
            flask.Markup(r'" name="') +
            flask.Markup.escape(name) +
            flask.Markup(r'" ') +
            form_value(name))

@app.template_filter()
def user_link(user_name):
    return (flask.Markup(r'<a href="https://commons.wikimedia.org/wiki/User:') +
            flask.Markup.escape(user_name.replace(' ', '_')) +
            flask.Markup(r'">') +
            flask.Markup(r'<bdi>') +
            flask.Markup.escape(user_name) +
            flask.Markup(r'</bdi>') +
            flask.Markup(r'</a>'))

@app.template_global()
def authentication_area():
    if 'oauth' not in app.config:
        return flask.Markup()

    if 'oauth_access_token' not in flask.session:
        return (flask.Markup(r'<a id="login" class="navbar-text" href="') +
                flask.Markup.escape(flask.url_for('login')) +
                flask.Markup(r'">Log in</a>'))

    access_token = mwoauth.AccessToken(**flask.session['oauth_access_token'])
    identity = mwoauth.identify('https://commons.wikimedia.org/w/index.php',
                                consumer_token,
                                access_token)

    return (flask.Markup(r'<span class="navbar-text">Logged in as ') +
            user_link(identity['username']) +
            flask.Markup(r'</span>'))

@app.template_global()
def authenticated_session():
    if 'oauth_access_token' in flask.session:
        access_token = mwoauth.AccessToken(**flask.session['oauth_access_token'])
        auth = requests_oauthlib.OAuth1(client_key=consumer_token.key, client_secret=consumer_token.secret,
                                        resource_owner_key=access_token.key, resource_owner_secret=access_token.secret)
        return mwapi.Session(host='https://commons.wikimedia.org', auth=auth, user_agent=user_agent)
    else:
        return None


@app.route('/')
def index():
    return flask.render_template('index.html')

@app.route('/leaderboard')
def leaderboard():
    return flask.render_template('leaderboard.html')

@app.route('/task')
def task():
    if authenticated_session():
        return flask.render_template('task.html')
    else:
        return flask.redirect('/login')

@app.route('/basic-task')
def basic_task():
    return flask.render_template('basic_task.html')

@app.route('/api/task')
def get_task():
    available = os.listdir(os.path.join(__dir__ + '/jsonfiles'))
    task = random.choice(available)

    with open(os.path.join(__dir__ + '/jsonfiles', task)) as task_file:
        resp = flask.Response(json.dumps(json.load(task_file)), status=200, mimetype='application/json')
    resp.headers['Task'] = str(task)
    resp.headers['Progress'] = str(progress())
    return resp

@app.route('/api/save', methods=['POST'])
def save():
    mwapi_auth_session = authenticated_session()
    if not mwapi_auth_session   :
        return flask.abort(404)

    data = False
    if flask.request.method == 'POST':
        data = flask.request.get_json(force=True)
    else:
        return flask.abort(400)

    new_data = mwapi_auth_session.get(action='query', prop='revisions', titles=data['page'], rvslots='main', rvprop='content', rvlimit='1')
    pageid = list(new_data['query']['pages'].keys())[0]
    pagecontent = new_data['query']['pages'][pageid]['revisions'][0]['slots']['main']['*']
    wikitext = mwparserfromhell.parse(pagecontent)
    for template in wikitext.filter_templates():
        if template.name.strip() == 'Musikverket-image':
            for param in template.params:
                if param.name.strip() == 'description':
                    if '{{' in param.value: #done allready
                        return flask.abort(400)

                    new_param_value = ' {{sv|' + str(param.value).replace('\n', '') + '}}\n{{en|' + data['trans'] + '}}\n'
                    param.value = new_param_value

    csrf_token = mwapi_auth_session.get(action='query', meta='tokens', type='csrf')['query']['tokens']['csrftoken']

    edit = mwapi_auth_session.post(action='edit', pageid=pageid, text=str(wikitext), summary='added english translation of description with musikverket-description-translation-tool', token=csrf_token)

    os.remove('jsonfiles/' + data['source'])
    print(edit) # for logging
    return flask.jsonify(data)

@app.route('/praise', methods=['GET', 'POST'])
def praise():
    csrf_error = False
    if flask.request.method == 'POST':
        if submitted_request_valid():
            flask.session['praise'] = flask.request.form.get('praise', 'praise missing')
        else:
            csrf_error = True
            flask.g.repeat_form = True

    session = authenticated_session()
    if session:
        userinfo = session.get(action='query', meta='userinfo', uiprop='options')['query']['userinfo']
        name = userinfo['name']
        gender = userinfo['options']['gender']
        if gender == 'male':
            default_praise = 'Praise him with great praise!'
        elif gender == 'female':
            default_praise = 'Praise her with great praise!'
        else:
            default_praise = 'Praise them with great praise!'
    else:
        name = None
        default_praise = 'You rock!'

    praise = flask.session.get('praise', default_praise)

    return flask.render_template('praise.html',
                                 name=name,
                                 praise=praise,
                                 csrf_error=csrf_error)

@app.route('/login')
def login():
    redirect, request_token = mwoauth.initiate('https://commons.wikimedia.org/w/index.php', consumer_token, user_agent=user_agent)
    flask.session['oauth_request_token'] = dict(zip(request_token._fields, request_token))
    return flask.redirect(redirect)

@app.route('/auth-callback')
def oauth_callback():
    request_token = mwoauth.RequestToken(**flask.session.pop('oauth_request_token'))
    access_token = mwoauth.complete('https://commons.wikimedia.org/w/index.php', consumer_token, request_token, flask.request.query_string, user_agent=user_agent)
    flask.session['oauth_access_token'] = dict(zip(access_token._fields, access_token))
    return flask.redirect(flask.url_for('index'))


def full_url(endpoint, **kwargs):
    scheme = flask.request.headers.get('X-Forwarded-Proto', 'http')
    return flask.url_for(endpoint, _external=True, _scheme=scheme, **kwargs)

def submitted_request_valid():
    """Check whether a submitted POST request is valid.

    If this method returns False, the request might have been issued
    by an attacker as part of a Cross-Site Request Forgery attack;
    callers MUST NOT process the request in that case.
    """
    real_token = flask.session.pop('csrf_token', None)
    submitted_token = flask.request.form.get('csrf_token', None)
    if not real_token:
        # we never expected a POST
        return False
    if not submitted_token:
        # token got lost or attacker did not supply it
        return False
    if submitted_token != real_token:
        # incorrect token (could be outdated or incorrectly forged)
        return False
    if not (flask.request.referrer or '').startswith(full_url('index')):
        # correct token but not coming from the correct page; for
        # example, JS running on https://tools.wmflabs.org/tool-a is
        # allowed to access https://tools.wmflabs.org/tool-b and
        # extract CSRF tokens from it (since both of these pages are
        # hosted on the https://tools.wmflabs.org domain), so checking
        # the Referer header is our only protection against attackers
        # from other Toolforge tools
        return False
    return True

@app.after_request
def deny_frame(response):
    """Disallow embedding the tool’s pages in other websites.

    If other websites can embed this tool’s pages, e. g. in <iframe>s,
    other tools hosted on tools.wmflabs.org can send arbitrary web
    requests from this tool’s context, bypassing the referrer-based
    CSRF protection.
    """
    response.headers['X-Frame-Options'] = 'deny'
    return response

def progress():
    n_tasks = len(os.listdir(__dir__ + '/jsonfiles'))
    return 100 - (100 * float(n_tasks)/1281)
