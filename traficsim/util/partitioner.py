from abc import abstractclassmethod

class Partitioner:

    @abstractclassmethod
    def getPartition(self,key) -> int:
        pass

    @abstractclassmethod   
    def numPartitions(self) -> int:
        pass