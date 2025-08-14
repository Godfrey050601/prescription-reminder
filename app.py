from flask import Flask, render_template, request
app = Flask(__name__)

@app.route('/')
def index():
    return "<h1>Welcome to Prescription Reminder</h1><p>Flask app with background job scheduler for prescription reminders</p>"

if __name__ == '__main__':
    app.run(debug=True)
