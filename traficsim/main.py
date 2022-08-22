import errno
import getopt
import itertools
import logging
import swiftclient
import fsspec
from fsspec.implementations.local import LocalFileSystem
import os
from keystoneauth1 import session
from keystoneauth1.identity import v3
import subprocess
import sys
import uuid
import json
from collections import defaultdict
from pathlib import Path
from datetime import datetime

import uuid as uuid
from pytz import timezone
from traficsim.util.murmur3_partitioner import Murmur3Partitioner
import pandas as pd
from lxml import etree

from traficsim import setup_logging

logger = logging.getLogger(__name__)


def run_flow_router(sim_uuid, sim_params, interval):
    if not os.path.exists(Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}')):
        try:
            os.makedirs(Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}'))
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise

    cmd = 'python3 {script_path} -n {net_path} -d {detectors_path} -f {conf_path} -o {output_path} -e {flows_path} '.format(
        script_path=Path(os.getenv('SUMO_HOME', '/usr/share/sumo')) / Path('tools/detector/flowrouter.py'),
        net_path=Path.cwd() / Path('config/updated.net.xml'),
        detectors_path=Path.cwd() / Path('config/detectors.xml'),
        conf_path=Path.cwd() / Path('config/wcfg.csv'),
        output_path=Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/route.xml'),
        flows_path=Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/flow.xml'),
        interval=interval
    )
    logger.info("Starting flowrouter with command: {}".format(cmd))
    subprocess.run(cmd, shell=True)
    logger.info("flowrouter end")


def create_flow_file(sim_uuid, sim_params, attrs):
    tree = etree.parse(Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/route.xml'))

    additional_el = tree.getroot()

    vtype = etree.SubElement(additional_el, "vType", )
    for key in attrs.keys():
        vtype.attrib[key] = attrs[key]

    with open(Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/route.xml'), 'wb') as f:
        tree.write(f, encoding='utf-8', pretty_print=True)
    logger.info(
        "{attrs} \n saved in {file}".format(attrs=attrs,
                                            file=str(Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/route.xml'))))


def call_dua_router(sim_uuid, sim_params, algo):
    cmd = 'duarouter --output-file {output_file} --save-configuration {output_config} ' \
          '--net-file {netfile} --route-files {routefile},{flowfile} --vtype-output {vtypefile} ' \
          '--routing-algorithm {algo} --weight-period 50 -v'.format(
        output_file=Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/DUAout.xml'),
        output_config=Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/duaCFG.xml'),
        conf_path=Path.cwd() / Path('simulation/Data/Config/wcfg.csv'),
        netfile=Path.cwd() / Path('config/updated.net.xml'),
        routefile=Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/route.xml'),
        flowfile=Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/flow.xml'),
        vtypefile=Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/vtype.xml'),
        algo=algo
    )
    logger.info("Running duarouter config with command: {}".format(cmd))
    subprocess.run(cmd, shell=True)
    logger.info("duarouter config end")

    cmd = 'duarouter -c {conf_file} -v'.format(
        conf_file=Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/duaCFG.xml'),

    )
    logger.info("Running duarouter with command: {}".format(cmd))
    subprocess.run(cmd, shell=True)
    logger.info("duarouter end")


def run_sumo(sim_uuid, sim_params):
    cmd = "sumo --save-configuration {config_file} --net-file {net_file} --route-files {routefile} " \
          "--additional-files {aditionalfile} --time-to-teleport 3600 --end 86400 --ignore-route-errors true " \
          "--device.rerouting.adaptation-steps 18 --device.rerouting.adaptation-interval 10 " \
          "--duration-log.statistics true --log {logfile} --step-length 0.1 --threads 4 " \
          "--statistic-output {statfile}".format(
        config_file=Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/sumo.sumocfg'),
        net_file=Path.cwd() / Path('config/updated.net.xml'),
        routefile=Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/DUAout.xml'),
        aditionalfile=Path.cwd() / Path('config/additional.xml'),
        logfile=Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/log.xml'),
        statfile=Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/stat.xml'))
    logger.info("Running sumo config with command: {}".format(cmd))
    subprocess.run(cmd, shell=True)

    cmd = "sumo -c {config_file}".format(
        config_file=Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/sumo.sumocfg'))
    subprocess.run(cmd, shell=True)
    return


def get_swift_conn():
    auth_url = os.getenv('OS_AUTH_URL')
    app_cred_id = os.environ.get('OS_APPLICATION_CREDENTIAL_ID')
    app_cred_secret = os.environ.get('OS_APPLICATION_CREDENTIAL_SECRET')

    auth = v3.ApplicationCredential(auth_url=auth_url,
                                    application_credential_id=app_cred_id,
                                    application_credential_secret=app_cred_secret)
    keystone_session = session.Session(auth=auth)
    swift_conn = swiftclient.Connection(session=keystone_session)
    return swift_conn


def upload_results(sim_uuid, sim_params):
    swift_conn = get_swift_conn()
    local_fs = LocalFileSystem()

    for root, subdirs, files in local_fs.walk(Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}')):
        for filename in files:
            file_path = os.path.join(root, filename)
            print('Uploading file %s (full path: %s)' % (filename, file_path))
            with open(file_path, 'rb') as local_file:
                swift_conn.put_object(
                    'TraficSim',
                    f'{sim_uuid}/{sim_params}/{filename}',
                    contents=local_file,
                    content_type='text/plain')


# Debug area
def print_help():
    print('Какво пишеш? Погледни си кода!')


def main():
    logger.info('traficsim goes brrrrrr')
    sim_uuid = uuid.uuid4()
    algo = ""
    minGap = ""
    tau = ""

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hu:a:m:t:", ['help', 'uuid=', 'algo=', 'minGap=', 'tau='])
    except getopt.GetoptError as error:
        logger.error(error)
        print_help()
        sys.exit(2)
    for opt, arg in opts:
        if opt in ('-h', "--help"):
            print_help()
            sys.exit()
        elif opt in ('-u', '--uuid'):
            sim_uuid = arg
        elif opt in ('-a', '--algo'):
            algo = str(arg)
        elif opt in ('-m', '--minGap'):
            minGap = arg
        elif opt in ('-t', '--tau'):
            tau = arg

    print(f'--uuid={uuid}')
    print(f'--algo={algo}')
    print(f'--minGap={minGap}')
    print(f'--tau={tau}')
    print(f'cwd={Path.cwd()}')
    # routingAlgorithm = ['dijkstra', 'astar', 'CH']
    # minGap = [1, 1.5, 2, 2.5, 3]
    # tau = [1, 1.25]

    # result_dict = defaultdict(list)
    # for algo, m, t in itertools.product(routingAlgorithm, minGap, tau):

    sim_params = "algo={}_minGap={}_tau={}".format(algo, minGap, tau)
    # if partitioner.getPartition(sim_params) == task_index:
    start_dt = datetime.now(timezone('Europe/Sofia'))
    print(f'Start: {start_dt}')
    run_flow_router(sim_uuid, sim_params, 50)

    attrs = {
        'id': 'vdist1',
        'vClass': 'passenger',
        'color': '1,0,0',
        'carFollowModel': 'KraussOrig1',
        'minGap': f'{minGap}',
        'tau': f'{tau}'
    }

    create_flow_file(sim_uuid, sim_params, attrs)

    call_dua_router(sim_uuid, sim_params, algo)
    run_sumo(sim_uuid, sim_params)

    json_object = json.dumps(attrs, indent=4)
    with open(Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/attrs.json'), "w") as outfile:
        outfile.write(json_object)

    upload_results(sim_uuid, sim_params)
    end_dt = datetime.now(timezone('Europe/Sofia'))
    print(f'End: {end_dt}')
    print(f'Duration: {end_dt - start_dt}')

    return


if __name__ == '__main__':
    setup_logging()
    main()
