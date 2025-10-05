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
    
    return code