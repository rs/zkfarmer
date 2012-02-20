ZooKeeper Farmer
================

ZkFarmer is a set of tools to easily manage distributed server farms using [Apache ZooKeeper](http://zookeeper.apache.org/).

With ZkFarmer, each server registers itself in one or several farms. Thru this registration, hosts can expose arbitrary information about their status.

On the other end, ZkFarmer helps consumers of the farm to maintain a configuration file in sync with the list of hosts registered in the farm with their respective configuration.

In the middle, ZkFarmer helps monitoring and administrative services to easily read and change the configuration of each host.

Connecting to Zookeeper
-----------------------

All subcommands of `zkfarmer` needs the full list of your ZooKeeper cluster hosts. You can either pass the list of ZooKeeper hosts via the `ZKHOST` environment variable or via the `--host` parameter. Hosts are host:port pairs separated by commas. All examples in this documentation assume you have your ZooKeeper hosts configured in your environment.

Joining a Farm
--------------

The `zkfarmer join` command is used on each host to register itself in a farm. The command will create an `ephemeral` znode in ZooKeeper that will live until the program isn't killed. As this command will never return, you should start it as a service using something like `upstart`, `daemontools` or `launchd`. If the host crash or if you kill `zkfarmer`, the host's znode will be automatically removed by ZooKeeper.

This command takes two arguments, `farm path` and `conf path`. The `farm path` is the path to an existing znode on the ZooKeeper server used to store the hosts of a given farm.

The `conf path` is the path to the local configuration to be associated with the host. This configuration can be a JSON file or a DJB like directory configuration. DJB directory is the preferred format for this configuration as it offers better flexibility. With a DJB like directory configuration format, each directory is a dictionary and each file is a key with its contents as value.

Once started, the content of the local configuration is transformed into JSON and stored in an `ephemeral` znode on ZooKeeper. The znode is named after the IP of the host assigned to the default route.

Lets start the following command from the 1.2.3.4 host:

    zkfarmer join /services/db /var/service/db

Lets assume `/var/service/db` is a directory containing the following structure:

    hostname
    enabled
    mysql/
      replication_delay

The `zkfarmer join` command transformed it to the following JSON object and stored it the `/services/db/1.2.3.4` znode:

    {
      "hostname": "db-01.example.com",
      "enabled": "0",
      "mysql": {"replication_delay": "0"}
    }

While the `zkfarmer join` command is running, this znode will be maintained up to date with local configuration and vis versa. For instance if you do an `echo 1 > /var/service/db/enabled` from the host, the change will be immediately reflected into the znode JSON content. Any change on the content of the znode will also update the local configuration on the host.

Syncing Farm Configuration
--------------------------

On the other end, consumers of the service provided by a farm may not have the ability to keep a permanent connection to ZooKeeper in order to maintain an up-to-date view of the farm state. ZkFarmer can do this for you by maintaining local configuration file reflecting the current status of the farm. PHP and JSON formats are currently supported, more formats may come in the future.

To do this, use the `zkfarmer export` command. As for the `join` command, it will run forever so you may launch it as a service. While the command is running, the destination configuration file will be synchronized with the content of the farm in real time.

Lets take our previous `/services/db` farm. Running the `zkfarm export /services/db /data/web/conf/database.php` will export and maintain the `/data/web/conf/database.php` file with the followoing content:

    <?php
    return array
    (
        "1.2.3.4" => array
        (
            "hostname" => "db-01.example.com",
            "enabled" => "0",
            "mysql" => array("replication_delay" => "0"),
        ),
        "1.2.3.5" => array
        (
            "hostname" => "db-02.example.com",
            "enabled" => "1",
            "mysql" => array("replication_delay" => "1"),
        ),
        ...
    );

Additionnaly, you can ask ZkFarmer to execute a command each time the configuration is updated. This command can, for instance, flush some cache, reload the conf file in your application etc.

It's possible to filter out some nodes from the exported configuration if it matches certain criteria so you don't have to filter them out at reading. The `--filters` parameter can be used to the that. A filter predicate is a field path followed by a comparison operator and a valud. Supported operator are one of `=`, `!=`, `>`, `<`, `>=`, `<=`. A predicate containing only a field path can be used to ensure the field is present whatever its value. A field path prefixed by a `!` means the oposite.

Lets take our previous `/services/db` farm. Running the `zkfarm export --filters enabled=1 /services/db /data/web/conf/database.php` will export and maintain the `/data/web/conf/database.php` file with the followoing content:

    <?php
    return array
    (
        "1.2.3.5" => array
        (
            "hostname" => "db-02.example.com",
            "enabled" => "1",
            "mysql" => array("replication_delay" => "1"),
        ),
        ...
    );

Managing Farms
--------------

ZkFarmer comes with some other commands to list, read and write farms content.

### List farms and hosts

The `zkfarm ls` command let you list znodes in ZooKeeper. If the listed znode contains ZkFarmer maintained host information, it can also show some fields associated to each listed host:

You can list all the farms you stored in `/services`:

    $ zkfarmer ls /services
    db
    cache
    search
    soft

You can explore the status of hosts in a farm:

    $ zkfarmer ls /services/db --fields hostname,enabled
    1.2.3.4          hostname=db-01.example.com, enabled=0
    1.2.3.5          hostname=db-02.example.com, enabled=1
    ...

To dump sub-fields, use dotted notation (ex: mysql.replication_delay).

### Retrieve an host field

The `zkfarm get` can return the value of a given field for a host:

    $ zkfarmer get /services/db/1.2.3.4 enabled
    0

### Edit an host field

You can also change the value of field for a given host from anywhere on your network like this:

    $ zkfarmer set /services/db/1.2.3.4 enabled 1

The local configuration on the host will immediately get updated as well as all consumers currently exporting this farm.

### Farm properties

The `zkfarmer set` and `zkfarmer get` commands can be used to store and read properties of a farm. This can be useful for monitoring tools for instance. You could store the minimum number of working nodes required before to throw an alert. To do that, you need two properties, `min_nodes` and `working_filter` for instance:

    $ zkfarmer set /services/db min_node 30
    $ zkfarmer set /services/db working_filter enabled=1

Then to check the health of a service, run the following nagios compatible script:

    #!/bin/sh

    farm=$1
    min_node=$(zkfarmer get $farm min_node)
    working_filters=$(zkfarmer get $farm working_filters)
    if [ $(kfarmer ls --filters $working_filters $farm | wc -l) -gt $min_node ]
    then
        echo "OK"
    else
        echo "CRITICAL"
    fi

Run it as follow:

    $ zkfarmer_check /services/db
