"""Camera UI acceptance using Edge's synthetic camera; no physical camera access."""
import argparse
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:3011')
    parser.add_argument('--output', default='test-artifacts')
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True, args=[
            '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'])
        context = browser.new_context(viewport={'width':1440, 'height':1000})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.url)
        page.locator('#auth-toggle').click()
        page.locator('#auth-username').fill('live_' + str(time.time_ns()))
        page.locator('#auth-password').fill('camera-test-password')
        page.locator('#auth-submit').click()
        expect(page.locator('#auth-dialog')).not_to_be_visible()
        page.locator('#camera-open').click()
        page.wait_for_function('poseState.frames >= 4', timeout=60000)
        expect(page.locator('#pose-overlay')).to_be_visible()
        expect(page.locator('#pose-metrics > div')).to_have_count(6)
        page.screenshot(path=str(output / 'realtime-desktop.png'), full_page=True)
        page.locator('#pose-toggle').click()
        frames = page.evaluate('poseState.frames')
        page.wait_for_timeout(500)
        assert page.evaluate('poseState.frames') == frames
        expect(page.locator('#pose-overlay')).not_to_be_visible()
        page.locator('#pose-toggle').click()
        page.wait_for_function('poseState.frames >= 3', timeout=30000)
        page.locator('#capture-view').select_option('front')
        page.wait_for_function('poseState.frames >= 3', timeout=30000)
        page.locator('#calibrate').click()
        canvas = page.locator('#calibration-canvas')
        box = canvas.bounding_box()
        canvas.click(position={'x':box['width']/2, 'y':box['height']*.15})
        canvas.click(position={'x':box['width']/2, 'y':box['height']*.85})
        expect(page.locator('#capture-pixels')).not_to_have_value('')
        page.wait_for_function('poseState.frames >= 3', timeout=30000)
        page.locator('#calibration-clear').click()
        page.wait_for_function('poseState.frames >= 3', timeout=30000)
        page.set_viewport_size({'width':390, 'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(output / 'realtime-mobile.png'), full_page=True)
        page.evaluate('window.testCameraTrack = state.stream.getVideoTracks()[0]')
        page.locator('nav [data-page="reports"]').click()
        page.wait_for_function('poseState.socket === null && window.testCameraTrack.readyState === "ended"')
        expect(page.locator('#pose-panel')).not_to_be_visible()
        page.locator('nav [data-page="analyze"]').click()
        page.locator('#camera-open').click()
        page.wait_for_function('poseState.frames >= 3', timeout=30000)
        page.locator('#camera-close').click()
        page.wait_for_function('poseState.socket === null && state.stream === null')
        assert not errors, errors
        (output / 'realtime-result.json').write_text(json.dumps({
            'passed':True, 'camera':'synthetic', 'pageErrors':errors,
            'checks':['continuous frames','stop/restart','settings reconnect','calibration reconnect',
                      'mobile layout','page switch releases camera','close camera']}, indent=2), encoding='utf-8')
        context.close()
        browser.close()


if __name__ == '__main__':
    main()
