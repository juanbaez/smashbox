from smashbox.utilities import *
from functools import wraps
import errno
import os
import signal
import owncloud

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


LOCK_NONE = 0
LOCK_SHARED = 1
LOCK_EXCLUSIVE = 2

ALL_OPERATIONS = [
    # a new file can be uploaded/created (file target does not exist)
    'upload',
    # a file can overwrite an existing one
    'upload_overwrite',
    # rename file to new name, all within the shared folder
    'rename',
    # move a file from outside the shared folder into the shared folder
    'move_in',
    # move a file from outside the shared folder and overwrite a file inside the shared folder
    # (note: SabreDAV automatically deletes the target file first before moving, so requires DELETE permission too)
    'move_in_overwrite',
    # move a file already in the shared folder into a subdir within the shared folder
    'move_in_subdir',
    # move a file already in the shared folder into a subdir within the shared folder and overwrite an existing file there
    'move_in_subdir_overwrite',
    # move a file to outside of the shared folder
    'move_out',
    # move a file out of a subdir of the shared folder into the shared folder
    'move_out_subdir',
    # delete a file inside the shared folder
    'delete',
    # create folder inside the shared folder
    'mkdir',
    # delete folder inside the shared folder
    'rmdir',
]

SHARED_DIR_NAME = 'shared-dir'

testsets = [
    {
        'locks': [
            {
                'lock': LOCK_EXCLUSIVE,
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
    except TimeoutError:
        # FIXME Issue raised https://github.com/owncloud/client/issues/4037
        error_check(False, 'Sync client did not terminate within 10 seconds')

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


#  TODO ove this into cernbox
class TimeoutError(Exception):
    pass


#  TODO ove this into cernbox
def timeout(seconds=10, error_message=os.strerror(errno.ETIME)):
    def decorator(func):
        def _handle_timeout(signum, frame):
            raise TimeoutError(error_message)

        def wrapper(*args, **kwargs):
            signal.signal(signal.SIGALRM, _handle_timeout)
            signal.alarm(seconds)
            try:
                result = func(*args, **kwargs)
            finally:
                signal.alarm(0)
            return result

        return wraps(func)(wrapper)

    return decorator


#  TODO ove this into cernbox
@timeout(10)
def run_ocsync_timeout(local_folder, remote_folder="", n=None, user_num=None):
    run_ocsync(local_folder, remote_folder, n, user_num)


#  TODO Add docs
class LockProvider:
    def __init__(self, oc_api):
        self.oc_api = oc_api

    def lock(self, lock_level, user, path):
        try:
            self.oc_api.make_ocs_request(
                'POST',
                'dev',
                'files_lockprovisioning/%i/%s/%s' % (lock_level, user, path)
            )
        except owncloud.ResponseError as err:
            logger.error(err.get_resource_body())
            raise err

    def change_lock(self, lock_level, user, path):
        try:
            self.oc_api.make_ocs_request(
                'PUT',
                'dev',
                'files_lockprovisioning/%i/%s/%s' % (lock_level, user, path)
            )
        except owncloud.ResponseError as err:
            logger.error(err.get_resource_body())
            raise err

    def is_locked(self, lock_level, user, path):
        try:
            kwargs = {'accepted_codes':  [100, 101]}
            res = self.oc_api.make_ocs_request(
                'GET',
                'dev',
                'files_lockprovisioning/%i/%s/%s' % (lock_level, user, path),
                **kwargs
            )

            import xml.etree.ElementTree as ET
            tree = ET.fromstring(res.content)
            code_el = tree.find('meta/statuscode')

            return int(code_el.text) == 100

        except owncloud.ResponseError as err:
            logger.error(err.get_resource_body())
            raise err

    def unlock(self, lock_level=None, user=None, path=None):
        ocs_path = 'files_lockprovisioning'

        if lock_level is not None:
            ocs_path = '%s/%i' % (ocs_path, lock_level)

            if user is not None:
                ocs_path = '%s/%s/%s' % (ocs_path, user, path)

        try:
            self.oc_api.make_ocs_request(
                'DELETE',
                'dev',
                ocs_path
            )
        except owncloud.ResponseError as err:
            logger.error(err.get_resource_body())
            raise err
