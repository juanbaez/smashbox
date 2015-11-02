from smashbox.ocutilities.locking import *
from smashbox.utilities import *
import os
import signal

__doc__ = """

Test share permission enforcement
+--------+--------------------+-----------------------+
|  Step  |       Owner        |       Recipient       |
| Number |                    |                       |
+========+====================+=======================+
| 2      | Create work dir    | Create work dir       |
+--------+--------------------+-----------------------+
| 3      | Create test folder |                       |
+--------+--------------------+-----------------------+
| 4      | Lock folder        |                       |
+--------+--------------------+-----------------------+
| 6      |                    | Check locking         |
|        |                    | enforcement for every |
|        |                    | operation             |
+--------+--------------------+-----------------------+
| 7      | Final              | Final                 |
+--------+--------------------+-----------------------+

Data Providers:

  sharePermissions_matrix: Permissions to be applied to the share,
                                combined with the expected result for
                                every file operation

"""


SHARED_DIR_NAME = 'shared-dir'

testsets = [
    {
        'locks': [
            {
                'lock': LockProvider.LOCK_EXCLUSIVE,
                'path': SHARED_DIR_NAME
            }
        ]
    }
]

use_locks = config.get('sharePermissions_matrix', testsets[0]['locks'])


@add_worker
def owner_worker(step):

    step(2, 'Create workdir')
    d = make_workdir()

    oc_api = get_oc_api()
    oc_api.login(config.oc_admin_user, config.oc_admin_password)
    lock_provider = LockProvider(oc_api)
    lock_provider.unlock()

    step(3, 'Create test folder')

    mkdir(os.path.join(d, SHARED_DIR_NAME))
    mkdir(os.path.join(d, SHARED_DIR_NAME, 'subdir'))
    createfile(os.path.join(d, SHARED_DIR_NAME, 'file.dat'), '0', count=1000, bs=1)
    createfile(os.path.join(d, SHARED_DIR_NAME, 'subdir', 'sub_file.dat'), '0', count=1000, bs=1)

    run_ocsync(d)

    step(4, 'Lock items')

    for lock in use_locks:
        fatal_check(
            lock_provider.is_locked(lock['lock'], config.oc_account_name, lock['path']) == False,
            'Resource is already locked'
        )

        lock_provider.lock(lock['lock'], config.oc_account_name, lock['path'])

        fatal_check(
            lock_provider.is_locked(lock['lock'], config.oc_account_name, lock['path']),
            'Resource should be locked'
        )

    step(6, 'Try to upload a file in locked item')

    createfile(os.path.join(d, SHARED_DIR_NAME, 'file2.dat'), '0', count=1000, bs=1)

    try:
        run_ocsync_timeout(d)
    except TimeoutError as err:
        # FIXME Issue raised https://github.com/owncloud/client/issues/4037
        logger.warning(err.message)

    step(7, 'Unlock item and sync again')

    for lock in use_locks:
        fatal_check(
            lock_provider.is_locked(lock['lock'], config.oc_account_name, lock['path']),
            'Resource is already locked'
        )

        lock_provider.unlock(lock['lock'], config.oc_account_name, lock['path'])

        fatal_check(
            lock_provider.is_locked(lock['lock'], config.oc_account_name, lock['path']) == False,
            'Resource should be locked'
        )

    step(8, 'Upload a file in unlocked item')

    run_ocsync(d)

    step(9, 'Final - Unlock everything')

    lock_provider.unlock()


#  TODO move the block below into cernbox
class TimeoutError(Exception):
    pass


def handler(signum, frame):
    raise TimeoutError('Sync client did not terminate in time')


def run_ocsync_timeout(local_folder, remote_folder="", n=None, user_num=None, seconds=10):
    signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)

    # This run_ocsync() may hang indefinitely
    run_ocsync(local_folder, remote_folder, n, user_num)

    signal.alarm(0)
