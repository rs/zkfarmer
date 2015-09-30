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

The `zkfarmer join` command is used on each host to register itself in a farm. The command will create an `ephemeral` znode in ZooKeeper that will live until the program is killed. As this command will never return, you should start it as a service using something like `upstart`, `daemontools` or `launchd`. If the host crash or if you kill `zkfarmer`, the host's znode will be automatically removed by ZooKeeper.

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

While this is not the primary goal of zkfarmer, you can also use it to synchronize a common configuration among a set of nodes. In this case, each node will use the same znode. You need to use the `--common` option when running `zkfarmer join` in this case. The JSON object will be stored in `/services/db/common` znode.

Usage for the `zkfarmer join` command:

    usage: zkfarmer join [-h] [-f {json,yaml,php,dir}] [-c] zknode conf

    Make the current host to join a farm.

    positional arguments:
      zknode                the ZooKeeper node path of the farm
      conf                  Path to the node configuration

    optional arguments:
      -h, --help            show this help message and exit
      -f {json,yaml,php,dir}, --format {json,yaml,php,dir}
                            set the configuration format
      --changed-cmd CMD     a command to be executed each time the configuration
                            change
      -c, --common          use a common zookeeper node instead of a dedicated node

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

Usage for the `zkfarmer export` command:

    usage: zkfarmer export [-h] [-f {json,yaml,php,dir}] [-c CMD] [-F FILTERS]
                           zknode conf

    Export and maintain a representation of the current farm' nodes' list with
    configuration to a local configuration file.

    positional arguments:
      zknode                the ZooKeeper node path to the farm
      conf                  path to the local configuration

    optional arguments:
      -h, --help            show this help message and exit
      -f {json,yaml,php,dir}, --format {json,yaml,php,dir}
                            set the configuration format
      -c CMD, --changed-cmd CMD
                            a command to be executed each time the configuration
                            change
      -F FILTERS, --filters FILTERS
                            filter out nodes which doesn't match supplied
                            predicates separeted by commas (ex:
                            enabled=0,replication_delay<10,!maintenance)

One-way Sync to Zookeeper
-------------------------

`zkfarmer export` will copy the configuration from zookeeper to the local filesystem while `zkfarmer join` will keep a znode in sync with a part of the local filesystem. In certain case, the bidirectional sync of `zkfarmer join` may be undesirable. In this case, you can use `zkfarmer import` which acts like `zkfarmer join` but does not react to remote changes. Only a local change will trigger a synchronisation to ZooKeeper. The most common use-case for this command is the use of `--common` flag.

Usage for the `zkfarmer import` command:

    usage: zkfarmer import [-h] [-f {json,yaml,php,dir}] [-c] zknode conf

    Import the current host configuration to a farm.

    positional arguments:
      zknode                the ZooKeeper node path of the farm
      conf                  Path to the node configuration

    optional arguments:
      -h, --help            show this help message and exit
      -f {json,yaml,php,dir}, --format {json,yaml,php,dir}
                            set the configuration format
      -c, --common          use a common zookeeper node instead of a dedicated node

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

### Unset a field

You can remove a field from a given host like this:
    
    $ zkfarmer unset /services/db/1.2.3.4 enabled

### Farm properties

The `zkfarmer set/unset` and `zkfarmer get` commands can be used to store and read properties of a farm. This can be useful for monitoring tools for instance. You could store the minimum number of working nodes required before to throw an alert. To do that, you need two properties, `min_nodes` and `running_filter` for instance:

    $ zkfarmer set /services/db min_node 30
    $ zkfarmer set /services/db running_filter enabled=1

Then to check the health of a service, run the following nagios compatible script:

    #!/bin/sh

    farm=$1
    min_node=$(zkfarmer get $farm min_node)
    running_filter=$(zkfarmer get $farm running_filter)
    if [ $(zkfarmer ls --filters $working_filters $farm | wc -l) -gt $min_node ]
    then
        echo "OK"
    else
        echo "CRITICAL"
        exit 2
    fi

Run it as follow:

    $ zkfarmer_check /services/db


Usage for the `zkfarmer set` command:

    usage: zkfarmer set [-h] zknode field value

    Set the value of a field of a given node or farm.

    positional arguments:
      zknode      the ZooKeeper node path to the farm or node
      field       the path of the field to set
      value       the new value

    optional arguments:
      -h, --help  show this help message and exit

Usage for the `zkfarmer unset` command:

    usage: zkfarmer unset [-h] zknode field

    Unset a field of a given node or farm.

    positional arguments:
      zknode      the ZooKeeper node path to the farm or node
      field       the path of the field to unset

    optional arguments:
      -h, --help  show this help message and exit

Usage for the `zkfarmer get` command:

    usage: zkfarmer get [-h] [-f {json,yaml,php}] zknode [field]

    Get node or farm information. If the optional <field> is specified, return the
    field's value. Otherwise, dump the whole configuration using the specified
    format.

    positional arguments:
      zknode                the ZooKeeper node path to the farm or node
      field                 the path of the field to return

    optional arguments:
      -h, --help            show this help message and exit
      -f {json,yaml,php}, --format {json,yaml,php}
                            set the configuration format (default is yaml)

Farm Monitoring
---------------

Fortunately, you don't have to write the above script by yourself, zkfarmer implements it own monitoring system thru the `check` command. Instead of `min_node` property, zkfarmer maintain a `size` property representing the maximum ever seen number of node in the cluster. You don't have to maintain this property by hand as zkfarmer will raise it each time a node is added to the farm. You may need to update it if you shrink your farm though.

The `zkfarmer check` command takes a maximum number of failed node as argument. This number could be an absolute number or a percentage of the farm. The default value is 10%. By default, all node which joined the farm will be counted as `running` nodes, but this is certainly not what you want. To inform zkfarmer how to detect running nodes, you may set the `running_filter` farm property with any number of predicates you need.

Here is an example of usage:

    $ zkfarmer get /services/db
    size: 17
    running_filter: 'enabled=1,running=1,mysql.replication_delay<60'

    $ zkfarmer check /services/db
    OK: 16/17 nodes running, 1 nodes failing, max allowed 10%

Usage for the `zkfarmer check` command:

    usage: zkfarmer check [-h] [-c MAX_FAILED_NODE] [-w WARN_FAILED_NODE] zknode

    Check a farm health regarding the number of failed node and return nagios
    compatible output. Failed node are max farm node - currently healthy nodes.
    Healthy nodes are by default all nodes currently in the farm. You may edit the
    `running_filter' farm property to filter out nodes maching criteria to counter
    as healthy node. The farm max node is stored in the `size' farm property and
    is raised by the `join' command with the farm is extended.If you shrink the
    farm, you may edit this property by hand.

    positional arguments:
      zknode                the ZooKeeper node path to the farm

    optional arguments:
      -h, --help            show this help message and exit
      -c MAX_FAILED_NODE, --max-failed-node MAX_FAILED_NODE
                            the max allowed number of failed nodes, can be a
                            number or a percentage (default 10%)
      -w WARN_FAILED_NODE, --warn-failed-node WARN_FAILED_NODE
                            if defined, number of failed node at which a warning
                            will be returned (must be lower than MAX_FAILED_NODE)

Farm State Aware Command Execution
----------------------------------

Not implemented yet

Usage for the `zkfarmer exec` command:

    usage: zkfarmer exec [-h] [-l LOCK_NAME] [-c CONCURRENCY] [-s SET]
                         [-a ALLOWED_HOUR_RANGES] [-r DELAY]
                         zknode

    This sub-command executes a local command in respect to various farm
    conditions and block until all conditions aren't met (will block forever if
    `--repeat' option is used). A lock can be acquired before to execute the
    command and can require that no more than N other clients acquired the lock
    before the local command is executed. A node property can be changed as soon
    as the command is executed, and restored to its previous value as soon command
    exit. The command can be prevented from being launched until the farm isn't
    healthy (see the `check' sub-command). Black hours can be set to prevent the
    command from being executed during peak hours. The command can be executed
    repetidely with given minimum delay between executions with respect to all
    other defined constraints.

    positional arguments:
      zknode                the ZooKeeper node path to the farm

    optional arguments:
      -h, --help            show this help message and exit
      -l LOCK_NAME, --lock LOCK_NAME
                            acquires a lock before to execute the command
      -c CONCURRENCY, --concurrency CONCURRENCY
                            allow N other concurrent clients to acquire the same
                            lock (default 1)
      -s SET, --set SET     set a node field just before execution and restore it
                            once done (foramt field.path=value
      -a ALLOWED_HOUR_RANGES, --allowed-hour-ranges ALLOWED_HOUR_RANGES
                            Ranges of hours between when the command can be
                            launched, outside of those range, this command will
                            block until next allowed range.
      -r DELAY, --repeat DELAY
                            repeat the command with a minimum delay of DELAY in
                            respect of other conditions (this option makes the
                            command to block forever, you should use something
                            like upstart to launch it
