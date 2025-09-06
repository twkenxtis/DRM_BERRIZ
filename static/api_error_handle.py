def api_error_handle(playback_info_code):
    if playback_info_code == 'FS_MD9000':
        return ('Join or Verify your Fanclub to enjoy various exclusive content and benefits')
    if playback_info_code == 'FS_MD1010':
        return ('This is a deleted media')
    if playback_info_code == 'FS_ER4040':
        return ('Service could not be found.')
    if playback_info_code == 'FS_ER5030':
        return ('Invalid request. Please check again.')
    if playback_info_code == 'FS_ER4040':
        return ('Service could not be found.')
    if playback_info_code == 'FS_ER4020':
        return ('Please log in again.')