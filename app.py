"""Entry point: `python app.py` or `flask --app app run`."""
from tracker import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)