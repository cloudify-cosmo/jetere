# jetere
Jenkins test reports using Django

## Installation

Prepare a Python 2.7.x virtualenv and activate it.

Run:
```bash
# Clone
git clone git@github.com:cloudify-cosmo/jetere.git

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Edit `config.yaml` and save it to `~/.jetere/config.yaml`.

# Run the server
```
./manage.py runserver
```

Happily browse to http://localhost:8000 and view your test reports.
