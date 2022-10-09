import errno
import getopt
import logging
from minio import Minio
from fsspec.implementations.local import LocalFileSystem
import os
import urllib3
import subprocess
import sys
import uuid
import json
from pathlib import Path
from datetime import datetime
import uuid as uuid
from pytz import timezone
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

    # Prepare detectors.xml
    tree = etree.parse(Path.cwd() / Path('config/detectors.xml'))
    for elem in tree.iter():
        if (elem.tag == 'inductionLoop' and elem.attrib.has_key('file')):
            elem.attrib['file'] = str(Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/detector_output.xml'))

    with open(Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/detectors.xml'), 'wb') as f:
        tree.write(f, encoding='utf-8', pretty_print=True)

    cmd = 'python3 {script_path} -n {net_path} -d {detectors_path} -f {conf_path1} -f {conf_path2} -o {output_path} -e {flows_path} '.format(
        script_path=Path(os.getenv('SUMO_HOME', '/usr/share/sumo')) / Path('tools/detector/flowrouter.py'),
        net_path=Path.cwd() / Path('config/DrivingHabits.net.xml'),
        detectors_path=Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/detectors.xml'),
        conf_path1=Path.cwd() / Path('config/wcfg.csv'),
        conf_path2=Path.cwd() / Path('config/hcfg.csv'),
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
        netfile=Path.cwd() / Path('config/DrivingHabits.net.xml'),
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
        net_file=Path.cwd() / Path('config/DrivingHabits.net.xml'),
        routefile=Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/DUAout.xml'),
        aditionalfile=Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/detectors.xml'),
        logfile=Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/log.xml'),
        statfile=Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/stat.xml'))
    logger.info("Running sumo config with command: {}".format(cmd))
    subprocess.run(cmd, shell=True)

    cmd = "sumo -c {config_file}".format(
        config_file=Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}/sumo.sumocfg'))
    subprocess.run(cmd, shell=True)
    return


def get_minio_client():
    endpoint_url = os.getenv('ENDPOINT-URL')
    access_key = os.environ.get('ACCESS-KEY')
    secret_key = os.environ.get('SECRET-KEY')

    return Minio(endpoint_url, access_key, secret_key, secure=False)


def upload_results(sim_uuid, sim_params):
    client = get_minio_client()

    bucket_name = os.environ.get('BUCKET-NAME')
    local_fs = LocalFileSystem()

    for root, subdirs, files in local_fs.walk(Path.cwd() / Path(f'data/{sim_uuid}/sim_{sim_params}')):
        for filename in files:
            file_path = os.path.join(root, filename)
            print('Uploading file %s (full path: %s)' % (filename, file_path))
            client.fput_object(bucket_name, f'{sim_uuid}/{sim_params}/{filename}', file_path, content_type='text/plain')


# Debug area
def print_help():
    print('Какво пишеш? Погледни си кода!')


def main():
    logger.info('traficsim goes brrrrrr')
    sim_uuid = uuid.uuid4()
    algo = "astar"
    interval = '10'
    minGap = "1"
    tau = "1"

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hu:a:m:t:i:", ['help', 'uuid=', 'algo=', 'minGap=', 'tau=', 'interval='])
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
        elif opt in ('-i', '--interval'):
            interval = arg

    print(f'--uuid={uuid}')
    print(f'--algo={algo}')
    print(f'--interval={interval}')
    print(f'--minGap={minGap}')
    print(f'--tau={tau}')
    print(f'cwd={Path.cwd()}')
    # routingAlgorithm = ['dijkstra', 'astar', 'CH']
    # minGap = [1, 1.5, 2, 2.5, 3]
    # tau = [1, 1.25]

    # result_dict = defaultdict(list)
    # for algo, m, t in itertools.product(routingAlgorithm, minGap, tau):

    sim_params = "algo={}_interval{}_minGap={}_tau={}".format(algo, interval, minGap, tau)
    # if partitioner.getPartition(sim_params) == task_index:
    start_dt = datetime.now(timezone('Europe/Sofia'))
    print(f'Start: {start_dt}')
    run_flow_router(sim_uuid, sim_params, interval)

    attrs = {
        'id': 'vdist1',
        'vClass': 'passenger',
        'color': '1,0,0',
        'carFollowModel': 'KraussOrig1',
        'interval': f'{interval}',
        'algo': f'{algo}',
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
