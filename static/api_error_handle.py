from typing import Optional

def api_error_handle(code: str) -> Optional[str]:
    if code == 'FS_MD9000':
        return 'Join or Verify your Fanclub to enjoy various exclusive content and benefits'
    if code == 'FS_MD1010':
        return 'This is a deleted media'
    if code == 'FS_ER4040':
        return 'Service could not be found.'
    if code == 'FS_ER5030':
        return 'Invalid request. Please check again.'
    if code == 'FS_ER4020':
        return 'Please log in again.'
    if code == 'FS_ER5010':
        return 'An error occurred during the service.'
    if code == 'FS_CU9900':
        return '(Fanclub) This is a fanclub-only content, Fanclub not subscribed'
    if code == 'FS_CU9999':
        return 'Community Info is Invalid.'
    if code == 'FS_CJ1010':
        return 'This Nickname already in use'
    if code == 'FS_CJ1011':
        return 'You are already a member in this community'
    if code == 'FS_CJ1014':
        return 'Invalid characters or spaces included, Please check input value'
    if code == 'FS_CM1010':
        return 'No content available, check are you in this community?'
    if code == 'FS_CJ1017':
        return 'You cannot join again within 24 hours you leave the community'
    if code == 'FS_CU2050':
        return 'This post mine be not found or deleted, Null post id.'
    return code