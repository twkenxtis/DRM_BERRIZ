    playback_contexts = LiveDownloader().get_playback_context(media_id)
    
    all_playback_infos = []

    for i, context in enumerate(playback_contexts):
        playback_info = PlaybackInfo(context)
        all_playback_infos.append(playback_info)

    first_info = all_playback_infos[0]
    print(f"code: {first_info.code}")
    print(f"status: {first_info.status}")
    
    # VOD related info
    if hasattr(first_info, 'duration'):
        print(f"duration: {first_info.duration}")
        print(f"orientation: {first_info.orientation}")
        print(f"is_drm: {first_info.is_drm}")
        print(f"assertion: {first_info.assertion}")
        print(f"widevine_license: {first_info.widevine_license}")
        print(f"playready_license: {first_info.playready_license}")
        print(f"fairplay_license: {first_info.fairplay_license}")
        print(f"fairplay_cert: {first_info.fairplay_cert}")
        print(f"hls_playback_url: {first_info.hls_playback_url}")
        print(f"dash_playback_url: {first_info.dash_playback_url}")

        if first_info.hls_adaptations:
            print("\n  HLS Adaptation Sets:")
            for i, adaptation in enumerate(first_info.hls_adaptations):
                print(f"    Adaptation Set {i}:")
                print(f"      Width: {adaptation.get('width')}")
                print(f"      Height: {adaptation.get('height')}")
                print(f"      Playback URL: {adaptation.get('playbackUrl')}")

        # Other info
        print(f"\ntracking_interval: {first_info.tracking_interval}")
        print(f"settlement_token: {first_info.settlement_token}")
    
    if len(first_info.hls_adaptations) > 0:
        print("  Adaptation Set 0:")
        print(f"    Width: {first_info.hls_adaptations[0]['width']}")
        print(f"    Height: {first_info.hls_adaptations[0]['height']}")
        print(f"    Playback URL: {first_info.hls_adaptations[0]['playbackUrl']}")

    if len(first_info.hls_adaptations) > 1:
        print("  Adaptation Set 1:")
        print(f"    Width: {first_info.hls_adaptations[1]['width']}")
        print(f"    Height: {first_info.hls_adaptations[1]['height']}")
        print(f"    Playback URL: {first_info.hls_adaptations[1]['playbackUrl']}")

    if len(first_info.hls_adaptations) > 2:
        print("  Adaptation Set 2:")
        print(f"    Width: {first_info.hls_adaptations[2]['width']}")
        print(f"    Height: {first_info.hls_adaptations[2]['height']}")
        print(f"    Playback URL: {first_info.hls_adaptations[2]['playbackUrl']}")
        
    if len(first_info.hls_adaptations) > 3:
        print("  Adaptation Set 3:")
        print(f"    Width: {first_info.hls_adaptations[3]['width']}")
        print(f"    Height: {first_info.hls_adaptations[3]['height']}")
        print(f"    Playback URL: {first_info.hls_adaptations[3]['playbackUrl']}")
        
    if len(first_info.hls_adaptations) > 4:
        print("  Adaptation Set 4:")
        print(f"    Width: {first_info.hls_adaptations[4]['width']}")
        print(f"    Height: {first_info.hls_adaptations[4]['height']}")
        print(f"    Playback URL: {first_info.hls_adaptations[4]['playbackUrl']}")
