# The project

This project is composed of a producer, a consumer and a database configuration helper.
* Producer: Gets website metrics and writes them into a kafka service provided by Aiven.io
* Consumer: Gets the messages stored in the kafka topic and writes them to a PostgreSQL database service provided by Aiven.io

# Configuring

The following configuration is valid for local testing (minikube) and for running the container in a cluster.

* Kafka and PostgreSQL services must be configured and running in avien.io
* Set up the secrets in the cluster where the containers are to run. This can be done by filling in the yaml files in `./config` then run `kubectl apply -f secretfile.yaml`. Those secrets correspond to the kafka and postgreSQL connections.
* Change the self documented configuration file `./config/config.yaml` to the environment specifications.
* Create the kafka topic named `website_availability`
* Configuring PostgreSQL:
    * Create the database `monitoring`.
    * Run `python ./src/__main__.py configure-database` so the required tables are created (needs the credentials stored in the local minikube or cluster being used)
    * Populate the table `website_availability.availability_monitor_config` with the websites to be monitored.

Make sure to configure the database so it allows more than 10 connections for the given user. There will be as many connections required as the amount of consumer containers to be run at the same time.



# Monitoring producer

Each producer needs a unique incremental ID starting at 1.
This way the producer know which of the configured websites they need to monitor, by working only with the range calculated using this ID and the websites per container defined in the `config.yaml` file.

When running in a cluster, the orchestrator must run enough producers to cover all the websites to be checked. The orchestrator can automatically calculate this number as follows:

`amount_of_producers = total_active_checks * yaml_config_websites_per_container`

Where:
* `total_active_checks`: Total amount of websites that the producers must actively check. Their amc_active must be true. They are stored in the table `monitoring.availability_monitor_config`
* `websites_per_container`: Number of websites each container will monitor. Currently located in the yaml config file.

In this case, the orchestrator will also assign an ID to each pod.

### Locally running the producer

The producer can be run locally using the following command:

```
python ./src/__main__.py start-producer [yaml_config_file_location] [id]
```

Where:
* `yaml_config_file_location`: Path to the config file.
* `ID`: one-based ID of the container from which it will extract the websites to monitor.

Make sure to run `minikube start` beforehand.

# Monitoring consumer

The consumer configuration is defined in the `./config/config.yaml` file.

Please remember to add more partitions to the kafka topic to match the amount of consumer to be run at the same time.

The consumer can be run locally using:

```
python ./src/__main__.py start-consumer [yaml_config_file_location]
```

Where:
* `yaml_config_file_location`: Path to the config file.

Make sure to run `minikube start` beforehand.

# Running the tests

### Using pycharm

* Mark the directories `src` and `tests` as sources and tests root respectivelly
* Right-click the tests folder, click on "Run 'pytest in tests'"
* PyCharm automatically runs the tests on a virtual environment.

### From command line

From the project root folder run the following:

```
cd tests;export PYTHONPATH="./../src";pytest
```

* Running all the tests: `pytest`
* Running unit tests: `pytest -m "not (integration_test or end_to_end)"`
* Running integration tests: `pytest -m "integration_test"`
    * They require postgresql to be installed: `apt install postgresql`.
* Running end to end tests: `pytest -m "end_to_end"`
    * A test environment must be online.
    * The file `./test/resources/config_it.yaml` needs to be configured accordingly.
    * The kafka topic must be created!

* Coverage: `coverage run -m pytest;coverage html`

# Docker containers and pod configurations

The included container and pod configurations require the secrets to be mounted as a volume so they can work.

Once this is done, they can be run as follows:

* Building and running the producer:

```
# Point to minkube environment, in case they are run locally
eval $(minikube docker-env)
# Building the image:
docker build -t monitoring_producer . -f ./docker/producer/Dockerfile 
# Submitting the pod to the cluster
kubectl create -f docker/producer/create-producer-pod.yaml
```

* Building and running the consumer:

```
# Point to minkube environment, in case they are run locally
eval $(minikube docker-env)
# Building the image:
docker build -t monitoring_consumer . -f ./docker/consumer/Dockerfile 
# Submitting the pod to the cluster
kubectl create -f docker/consumer/create-consumer-pod.yaml
```



### List of potential improvements:

* Instead of reading the kubernetes secrets and storing them in runtime so we can create the KafkaReader / Writer, those must be mounted in a volume defined a `docker-compose.yaml` file.
* Create a specific user in the DB that will have rights only to the tables it needs to work with.
* Configure automatic creation of topics in case it does not exist.
* Store the metrics in a timeseries database instead of postgreSQL since we are storing timed events
* Some common definitions of testing objects which are shared among tests (mocked configurations, etc) could be extracted into a shared testing helper module.
* Schema creation and evolution in the database using a company-standard tool
* The setup can be further improved to create the kafka topics initially and rest of configurations (right now it only creates de database schema and tables)
* The schemas in the SQL can be made configurable instead of hardcoded to be `monitoring`.
* Set as unique key the combination of request unix timestamp + url/url id so we don't get duplicated metrics
* Make the configure-database command accept credentials also instead of only kubernetes secrets.