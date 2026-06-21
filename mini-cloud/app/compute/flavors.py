# AWS-style instance types — user এর 8GB RAM এর মধ্যে রাখা হয়েছে
# vcpus=vCPU count, ram_mb=RAM in MiB, disk_gb=root disk size in GB
FLAVORS = {
    't1.nano':   {'vcpus': 1, 'ram_mb': 512,  'disk_gb': 5},
    't1.micro':  {'vcpus': 1, 'ram_mb': 1024, 'disk_gb': 10},
    't2.small':  {'vcpus': 1, 'ram_mb': 2048, 'disk_gb': 20},
    't2.medium': {'vcpus': 2, 'ram_mb': 2048, 'disk_gb': 20},
    't2.large':  {'vcpus': 2, 'ram_mb': 4096, 'disk_gb': 40},
    't2.xlarge': {'vcpus': 4, 'ram_mb': 4096, 'disk_gb': 40},
}


def get_flavor(name):
    return FLAVORS.get(name)


def list_flavors():
    return [{'name': k, **v} for k, v in FLAVORS.items()]
