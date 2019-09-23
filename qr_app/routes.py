import flask
import re
import base64
import functools
from qr_app import forms, models
from qr_app import app, flight_session, db

##### utils #####

def flight_required(f):

     @functools.wraps(f)
     def wrapper(*args, **kwargs):
         if not flight_session.alive():
             return flask.redirect(flask.url_for('new_flight'))
         return f(*args, **kwargs)

     return wrapper

def return_callback(default=None):

    def decorator(f):

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            r = f(*args, **kwargs)
            print("From return callback: ",flask.request.args)
            if 'callback' in flask.request.args:
                return flask.redirect(flask.url_for(flask.request.args.get('callback'), default=default))
            return r
        return wrapper
    return decorator


##### ROUTES #####

@app.route('/')
def homepage():
    return flask.redirect(flask.url_for("flights_history"))

@app.route('/new-flight',  methods=("GET", "POST"))
def new_flight():
    form = forms.NewFlight()

    if form.validate_on_submit():
        # Create soldiers
        commander    = models.Soldier.get_or_create(primary_key='id', id=form.soldier1.data, role="commander")
        pilot                   = models.Soldier.get_or_create(primary_key='id', id=form.soldier2.data, role="pilot")

        # Create coordinates objects
        coords_data = form.coordinates.data
        parse = re.match(r"Name:(?P<name>.+)_N:(?P<north>.+)_E:(?P<east>.+)_", coords_data).groupdict()      # TODO : add this as a method of the model
        coordinates = models.Coordinates.add_or_create(north=parse['north'], east=parse['east'], name=parse['name'])
        coordinates.add_to_db()


        # Create the flight
        new_flight = models.Flight()
        new_flight.add_soldier(commander)
        new_flight.add_soldier(pilot)
        new_flight.start_coord = coordinates
        new_flight.add_to_db()

        db.session.commit()
        flask.flash("Added flight {}".format(new_flight))
        set_flight(new_flight.id)
        return flask.redirect(flask.url_for('scan', flight=new_flight))

    else:
        print("Errors in form:",form.errors)

    return flask.render_template("new_flight.jin", form=form)

@app.route('/scan')
@flight_required
def scan():
    if flight_session.flight.ready_to_go():
        return flask.redirect(flask.url_for("homepage"))
    return flask.render_template("scan.jin")

@app.route('/qr-process/<component_id>')
def on_qr_find(component_id): # USELESS
    """
    :param component_id:  base64 encoded id of component
    """
    decoded = base64.b64decode(component_id).decode('utf-8')
    return flask.render_template("qr_process.jin")

@app.route('/flights') # TODO: CSS THIS
def flights_history():
    flights = {flight: flight.is_alive() for flight in models.Flight.query.all()}
    print(flights)
    sorted_flights = {f: flights[f] for f in sorted(flights, key=lambda i: flights[i], reverse=True)}
    return flask.render_template('flights_list.jin', flights=sorted_flights)

@app.route('/flight-details/<int:flight_id>')
def flight_details(flight_id):
    flight = models.Flight.query.get(flight_id)
    if not flight:
        return flask.redirect(flask.url_for('homepage'))    # TODO: Display an  404 page

    return flask.render_template("flight_details.jin", flight=flight)

@app.route('/end-flight', methods=("GET", "POST"))
def end_flight():
    form = forms.EndFlight()
    form.update_choices()
    if form.validate_on_submit():
        models.Flight.terminate_flight(form.flight_id.data)
        return flask.redirect(flask.url_for('homepage'))
    else:
        print('From <end_flight>, error on form:',form.errors)
    return flask.render_template('end_flight.jin', form=form)

@app.route("/api-test/<text>")
@return_callback
def test(text):
    print(text)
    return flask.redirect(flask.url_for('homepage'))

@app.route("/component-details/<int:comp_id>")
def component_details(comp_id):
    comp = models.Component.query.get(comp_id)
    if not comp:
        return flask.redirect(flask.url_for('homepage')) # TODO 404
    return flask.render_template('component_details.jin', component=comp)


# API
@app.route('/set-flight/<int:flight_id>', methods=('POST', 'GET'))
def set_flight(flight_id):
    callback = flask.request.args.get('callback', default=flask.url_for('homepage'), type=str)
    if not flight_id:
        return flask.redirect(callback)
    flight = models.Flight.query.get(flight_id)
    if not flight:
        return flask.redirect(callback)
    flight_session.set(flight)
    return flask.redirect(callback)

@app.route('/stop-flight/<int:flight_id>', methods=('POST', 'GET'))
def stop_flight(flight_id):
    models.Flight.terminate_flight(flight_id)
    print("Terminated flight {}".format(flight_id))
    if flight_id == flight_session.flight_id:
        flight_session.unset()
    callback = flask.request.args.get('callback', default=flask.url_for('homepage'), type=str)
    return flask.redirect(callback)

@app.route('/get-flight-id')
def get_flight_id():
    d = {'flight_id':  flight_session.flight_id}
    return flask.jsonify(d)

@app.route('/api-qr-process/<component_id>')
def on_qr_find_api(component_id):
    """
    :param component_id:  base64 encoded id of component
    """
    decoded_id = base64.b64decode(component_id).decode('utf-8')
    try:
        decoded_id = int(decoded_id)
    except:
        return flask.jsonify({'success':False, 'text':'Bad QR information'})

    comp = models.Component.get(decoded_id)

    if not comp:
        comp = models.Component(id=decoded_id,)

    if flight_session.get_current_flight().add_component(comp):
        resp = {'success':True,  "text": "Component No {} added to flight {}".format(comp.id, flight_session.flight_id)}
    else:
        resp = {'success':True, "text": "Component No {} already exist in flight {}".format(comp.id, flight_session.flight_id)}

    return flask.jsonify(resp)

