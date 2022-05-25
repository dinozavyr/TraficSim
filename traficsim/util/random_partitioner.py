from traficsim.util.partitioner import Partitioner
import random

class RandomPartitioner(Partitioner):
    """
    RandomPartitioner distributes data across the cluster based on Random number generator.
    """
    def __init__(self,partitions) -> None:
        self.partitions = partitions

    def getPartition(self,key) -> int:
        return random.randrange(0,self.partitions)

    def numPartitions(self) -> int:
        return self.partitions
