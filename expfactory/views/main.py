"""
views.py: part of expfactory package

Copyright (c) 2017-2022, Vanessa Sochat
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the copyright holder nor the names of its
  contributors may be used to endorse or promote products derived from
  this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""

from flask import render_template, request, redirect, session, url_for

from flask_wtf.csrf import generate_csrf
from expfactory.defaults import EXPFACTORY_LOGS
from expfactory.utils import get_post_fields, getenv

from expfactory.variables import get_runtime_vars
from expfactory.views.utils import perform_checks, clear_session
from expfactory.server import app
from .general import *
from .headless import *

import logging
import os
import json

from expfactory.forms import EntryForm

# Landing with url params ######################################################################

@app.route("/arc_tasks", methods=["GET"])
def arc_tasks_landing():
    # Getting url params
    username = request.args.get('username')
    user_id = request.args.get('user_id')
    experiment = request.args.get('experiment_id')
    return_url = request.args.get('return_url')

    print("DEBUG: ", return_url)

    # Generating a user in db
    subid = app.generate_subid(name=username, external_id=user_id)
    session["subid"] = subid

    # Setting session username and experiment
    session["username"] = username
    session["ext_user_id"] = username
    session["experiments"] = [experiment]  # list
    session["return_url"] = return_url

    # Setting whatever the fuck this is
    app.randomize = "y"

    # Whatever
    flash(
        'Participant ID: "%s" <br> Name %s <br> Randomize: "%s" <br> Experiments: %s'
        % (subid, username, app.randomize, str(session["experiments"]))
    )

    # Logging
    app.logger.info("Just landed as [user] %s" % username)
    app.logger.info(session)

    # Redirecting to start using current session
    return redirect(url_for("start"))

# LOGGING ######################################################################

file_handler = logging.FileHandler("%s/expfactory.log" % EXPFACTORY_LOGS)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.DEBUG)


# SECURITY #####################################################################


@app.after_request
def inject_csrf_token(response):
    response.headers.set("X-CSRF-Token", generate_csrf())
    return response


# EXPERIMENT PORTAL ############################################################


@app.route("/experiments")
def experiment_base():
    return render_template("experiments/index.html")


# Home portal to start experiments
@app.route("/", methods=["GET", "POST"])
def home():

    # A headless app can only be entered with a user token
    if app.headless:
        if "token" not in session:
            form = EntryForm()
            session["experiments"] = [
                os.path.basename(x) for x in app.experiments
            ]  # list
            return render_template("routes/entry.html", form=form)
        return redirect(url_for("next"))

    return portal()


# EXPERIMENT ROUTER ############################################################


@app.route("/save", methods=["POST"])
def save():
    """save is a view to save data. We might want to adjust this to allow for
    updating saved data, but given single file is just one post for now
    """
    if request.method == "POST":
        exp_id = session.get("exp_id")
        app.logger.debug("Saving data for %s" % exp_id)

        fields = get_post_fields(request)

        # Find the original experiment in the lookup - ensure data saved with name
        exp_id = app.lookup_experiment(exp_id)
        result_file = app.save_data(session=session, content=fields, exp_id=exp_id)
        app.logger.info("%s saved to %s." % (exp_id, result_file))

        experiments = app.finish_experiment(session, exp_id)
        app.logger.info("Finished %s, %s remaining." % (exp_id, len(experiments)))

        # Note, this doesn't seem to be enough to trigger ajax success
        return json.dumps({"success": True}), 200, {"ContentType": "application/json"}
    return json.dumps({"success": False}), 403, {"ContentType": "application/json"}


@app.route("/next", methods=["POST", "GET"])
def next():

    # Headless mode requires logged in user with token
    if app.headless and "token" not in session:
        return headless_denied()

    # To generate redirect to experiment
    experiment = app.get_next(session)

    if experiment is not None:
        meta = app.lookup[experiment]
        experiment_path = meta.get("folder", experiment)
        app.logger.debug("Next experiment is %s" % experiment)

        host_prefix = getenv("SCRIPT_NAME", default="")
        template = "%s/experiments/%s" % (host_prefix, experiment_path)

        # Do we have runtime variables?
        token = session.get("token")
        if app.vars is not None:
            variables = get_runtime_vars(
                token=token, varset=app.vars, experiment=experiment
            )
            template = "%s?%s" % (template, variables)

        return perform_checks(template=template, do_redirect=True, next=experiment)

    return redirect(url_for("finish"))


# Reset/Logout
@app.route("/logout", methods=["POST", "GET"])
def logout():

    # If the user has finished, clear session
    clear_session()
    return redirect(url_for("home"))


# Finish
@app.route("/finish", methods=["POST", "GET"])
def finish():

    subid = session.get("subid")
    return_url = session.get("return_url")

    # If the user has finished, clear session
    if subid is not None:

        # Filesystem will rename folder to _finished
        # Relational removes token so not accessible
        app.finish_user(subid)
        clear_session()
        # return render_template("routes/finish.html")
        return redirect(return_url)
    return redirect(url_for("home"))


@app.route("/start")
def start():
    """
    Start a battery.
    """
    return perform_checks("routes/start.html")
