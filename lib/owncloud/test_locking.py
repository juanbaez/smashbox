from smashbox.utilities import *

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

#  allowed_operations = config.get('sharePermissions_matrix', testsets[0]['allowed_operations'])
use_locks = config.get('sharePermissions_matrix', testsets[0]['locks'])


@add_worker
def owner_worker(step):

    step(2, 'Create workdir')
    d = make_workdir()

    step(3, 'Create test folder')

    mkdir(os.path.join(d, SHARED_DIR_NAME))
    mkdir(os.path.join(d, SHARED_DIR_NAME, 'subdir'))
    createfile(os.path.join(d, SHARED_DIR_NAME, 'file.dat'), '0', count=1000, bs=1)
    createfile(os.path.join(d, SHARED_DIR_NAME, 'subdir', 'sub_file.dat'), '0', count=1000, bs=1)

    run_ocsync(d)

    step(4, 'Shares folder with recipient')

    oc_api = get_oc_api()
    oc_api.login(config.oc_admin_user, config.oc_admin_password)

    for lock in use_locks:
        try:
            oc_api.make_ocs_request(
                'POST',
                'dev',
                'files_lockprovisioning/%i/%s/%s' % (lock['lock'], config.oc_account_name, lock['path'])
            )
        except owncloud.ResponseError as err:
            logger.error(err.get_resource_body)

    step(6, 'Final')
