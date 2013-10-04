VERSION = "1.1.0"

try:
    from .zkfarmer import ZkFarmer
except ImportError:
    # Maybe not everything is present, yet
    ZkFarmer = None
