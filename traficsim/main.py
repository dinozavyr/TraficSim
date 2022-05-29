import errno
import getopt
import itertools
import logging
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from datetime import datetime
from pytz import timezone
from traficsim.util.murmur3_partitioner import Murmur3Partitioner
import pandas as pd
from lxml import etree

from traficsim import setup_logging

logger = logging.getLogger(__name__)


def run_flow_router(sim_uuid, interval):
    if not os.path.exists(Path.cwd() / Path(f'data/sim_{sim_uuid}')):
        try:
            os.makedirs(Path.cwd() / Path(f'data/sim_{sim_uuid}'))
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise

    cmd = 'python3 {script_path} -n {net_path} -d {detectors_path} -f {conf_path} -o {output_path} -e {flows_path} '.format(
        script_path=Path(os.getenv('SUMO_HOME', '/usr/share/sumo')) / Path('tools/detector/flowrouter.py'),
        net_path=Path.cwd() / Path('config/updated.net.xml'),
        detectors_path=Path.cwd() / Path('config/detectors.xml'),
        conf_path=Path.cwd() / Path('config/wcfg.csv'),
        output_path=Path.cwd() / Path(f'data/sim_{sim_uuid}/route.xml'),
        flows_path=Path.cwd() / Path(f'data/sim_{sim_uuid}/flow.xml'),
        interval=interval
    )
    logger.info("Starting flowrouter with command: {}".format(cmd))
    subprocess.run(cmd, shell=True)
    logger.info("flowrouter end")


def create_flow_file(sim_uuid, attrs):
    tree = etree.parse(Path.cwd() / Path(f'data/sim_{sim_uuid}/route.xml'))

    additional_el = tree.getroot()

    vtype = etree.SubElement(additional_el, "vType", )
    for key in attrs.keys():
        vtype.attrib[key] = attrs[key]

    with open(Path.cwd() / Path(f'data/sim_{sim_uuid}/route.xml'), 'wb') as f:
        tree.write(f, encoding='utf-8', pretty_print=True)
    logger.info(
        "{attrs} \n saved in {file}".format(attrs=attrs, file=str(Path.cwd() / Path(f'data/sim_{sim_uuid}/route.xml'))))


def call_dua_router(sim_uuid, algo):
    cmd = 'duarouter --output-file {output_file} --save-configuration {output_config} --net-file {netfile} --route-files {routefile},{flowfile} --vtype-output {vtypefile} --routing-algorithm {algo} --weight-period 50 -v'.format(
        output_file=Path.cwd() / Path(f'data/sim_{sim_uuid}/DUAout.xml'),
        output_config=Path.cwd() / Path(f'data/sim_{sim_uuid}/duaCFG.xml'),
        conf_path=Path.cwd() / Path('simulation/Data/Config/wcfg.csv'),
        netfile=Path.cwd() / Path('config/updated.net.xml'),
        routefile=Path.cwd() / Path(f'data/sim_{sim_uuid}/route.xml'),
        flowfile=Path.cwd() / Path(f'data/sim_{sim_uuid}/flow.xml'),
        vtypefile=Path.cwd() / Path(f'data/sim_{sim_uuid}/vtype.xml'),
        algo=algo
    )
    logger.info("Running duarouter config with command: {}".format(cmd))
    subprocess.run(cmd, shell=True)
    logger.info("duarouter config end")

    cmd = 'duarouter -c {conf_file} -v'.format(
        conf_file=Path.cwd() / Path(f'data/sim_{sim_uuid}/duaCFG.xml'),

    )
    logger.info("Running duarouter with command: {}".format(cmd))
    subprocess.run(cmd, shell=True)
    logger.info("duarouter end")


def run_kraus_orig_1(sim_uuid, minGap, tau):

    cmd = "sumo --save-configuration {config_file} --net-file {net_file} --route-files {routefile} " \
          "--additional-files {aditionalfile} --time-to-teleport 3600 --end 86400 --ignore-route-errors true " \
          "--device.rerouting.adaptation-steps 18 --device.rerouting.adaptation-interval 10 " \
          "--duration-log.statistics true --log {logfile} --step-length 0.1 " \
          "--statistic-output {statfile} --summary-output {summaryfile}".format(
        config_file=Path.cwd() / Path(f'data/sim_{sim_uuid}/sumo.sumocfg'),
        net_file=Path.cwd() / Path('config/updated.net.xml'),
        routefile=Path.cwd() / Path(f'data/sim_{sim_uuid}/DUAout.xml'),
        aditionalfile=Path.cwd() / Path('config/additional.xml'),
        logfile=Path.cwd() / Path(f'data/sim_{sim_uuid}/log.xml'),
        statfile=Path.cwd() / Path(f'data/sim_{sim_uuid}/stat.xml'),
        summaryfile=Path.cwd() / Path(f'data/sim_{sim_uuid}/summary.xml'))
    logger.info("Running sumo config with command: {}".format(cmd))
    subprocess.run(cmd, shell=True)

    cmd = "sumo -c {config_file}".format(config_file=Path.cwd() / Path(f'data/sim_{sim_uuid}/sumo.sumocfg'))
    subprocess.run(cmd, shell=True)
    return


# Debug area
def print_help():
    print('Какво пишеш? Погледни си кода!')


def main():
    logger.info('traficsim goes brrrrrr')

    task_index = 0  # Index of the task used for partitioning of the input files
    num_tasks = 1  # Total number of task

    try:
        opts, args = getopt.getopt(sys.argv[1:], "hu:i:n:", ['help', 'task-index=', 'num-tasks='])
    except getopt.GetoptError as error:
        logger.error(error)
        print_help()
        sys.exit(2)
    for opt, arg in opts:
        if opt in ('-h', "--help"):
            print_help()
            sys.exit()
        elif opt in ('-i', '--task-index'):
            task_index = int(arg)
        elif opt in ('-n', '--num-tasks'):
            num_tasks = int(arg)

    routingAlgorithm = ['dijkstra', 'astar', 'CH']
    minGap = [1, 1.5, 2, 2.5, 3]
    tau = [1, 1.25]

    partitioner = Murmur3Partitioner(num_tasks)

    result_dict = defaultdict(list)
    for algo, m, t in itertools.product(routingAlgorithm, minGap, tau):

        sim_uuid = "algo={}_m={}_t={}".format(algo, m, t)
        if partitioner.getPartition(sim_uuid) == task_index:
            start_dt = str(datetime.now(timezone('Europe/Sofia')))
            run_flow_router(sim_uuid, 50)

            attrs = {
                'id': 'vdist1',
                'vClass': 'passenger',
                'color': '1,0,0',
                'carFollowModel': 'KraussOrig1',
                'minGap': f'{m}',
                'tau': f'{t}'
            }
            create_flow_file(sim_uuid, attrs)

            call_dua_router(sim_uuid, algo)
            run_kraus_orig_1(sim_uuid, m, t)
            end_dt = str(datetime.now(timezone('Europe/Sofia')))
            result_dict['algo'].append(algo)
            result_dict['minGap'].append(m)
            result_dict['tau'].append(t)
            result_dict['start'].append(start_dt)
            result_dict['end'].append(end_dt)
            tree = etree.parse(Path.cwd() / Path(f'data/sim_{sim_uuid}/stat.xml'))
            for el in list(tree.getroot()):
                for attr_name, attr_val in dict(el.attrib).items():
                    result_dict[f"{el.tag}_{attr_name}"].append(attr_val)
        else:
            logger.info(f"Task {task_index} skiping {sim_uuid}")
        break
    result_df = pd.DataFrame(result_dict)
    result_df.to_csv(Path.cwd() / Path(f'data/result_{task_index}_of_{num_tasks}.csv'))


if __name__ == '__main__':
    setup_logging()
    main()
