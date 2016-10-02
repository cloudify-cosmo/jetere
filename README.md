# jetere
Jenkins test reports using Django

## Installation

Prepare a Python 2.7.x virtualenv and activate it.

Run:
```bash
# Clone
git clone git@github.com:idanmo/jetere.git

# Install
./install.sh

# Create a superuser
./manage.py createsuperuser
```

## Configuration

* Point your browser to: http://localhost:8000/admin
* Login using superuser.
* Add a `Configuration` object with your jenkins server info.
* Point your browser to: http://localhost:8000/admin
* Create a `Job` object for each jenkins job you would like to generate test reports for.

Job object example:
* name: aaa
* jenkins_path: dir_system-tests/system-tests


# Run the server
```
./manage.py run --sync
```

The `--sync` flag will automatically sync `jetere` with jenkins every 1 minute.

Happily browse to http://localhost:8000 and view your test reports.


