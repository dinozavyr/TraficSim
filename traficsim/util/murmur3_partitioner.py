from traficsim.util.partitioner import Partitioner
import mmh3

class Murmur3Partitioner(Partitioner):
    """
    Murmur3Partitioner uniformly distributes data across the cluster based on MurmurHash values.
    """
    def __init__(self,partitions) -> None:
        self.partitions = partitions

    def getPartition(self,key) -> int:
        return mmh3.hash(key) % self.partitions

    def numPartitions(self) -> int:
        return self.partitions

