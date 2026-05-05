import json
import time
import random
import logging
import requests
import re
from uuid import uuid4
from urllib.parse import urlparse, parse_qs

log = logging.getLogger(__name__)

# OAuth 配置
OAUTH_URL = "https://m.4399api.com/openapi/oauth-callback.html?gamekey=44770&game_key=115716"
CAPTCHA_URL = "https://ptlogin.4399.com/ptlogin/captcha.do"
OAUTH_LOGIN_URL = "https://ptlogin.4399.com/oauth2/loginAndAuthorize.do?channel=&sdk=op&sdk_version=3.12.2.503"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def generate_uuid():
    return str(uuid4()).replace("-", "").upper()


def random_hex(length):
    return ''.join(random.choices('0123456789abcdef', k=length))


def recognize_captcha(img_bytes, ocr_engine, use_custom_model):
    """识别验证码"""
    try:
        if use_custom_model:
            result = ocr_engine.recognize(img_bytes)
            if result and len(result) >= 4:
                return result[:4].lower()
        else:
            # 假设 ocr_engine 有 classification 方法 (如 ddddocr)
            if hasattr(ocr_engine, 'classification'):
                result = ocr_engine.classification(img_bytes)
                if result and len(result) >= 4:
                    return result[:4].lower()
    except Exception as e:
        log.debug(f'验证码识别错误: {e}')
    return ""


def check_realname(session):
    """
    检查实名状态 (参考原 login_4399.py 逻辑)
    返回 (is_verified, reason)
    """
    try:
        # 尝试获取 Uauth Cookie
        uauth = session.cookies.get("Uauth")
        if not uauth or '|' not in uauth:
            return False, "缺少 Uauth Cookie"

        rand_time = uauth.split('|')[4]
        check_url = (
            f"http://ptlogin.4399.com/ptlogin/checkKidLoginUserCookie.do?"
            f"appId=kid_wdsj&gameUrl=http://cdn.h5wan.4399sj.com/microterminal-h5-frame?"
            f"game_id=500352&rand_time={rand_time}&nick=null"
            f"&onLineStart=false&show=1&isCrossDomain=1"
            f"&retUrl=http%253A%252F%252Fptlogin.4399.com%252Fresource%252Fucenter.html"
        )
        
        # 使用 allow_redirects=False 获取跳转链接
        resp = session.post(check_url, headers=HEADERS, allow_redirects=False, timeout=10)
        
        if resp.status_code in (301, 302):
            redirect_url = resp.headers.get('Location', '')
            if 'realname' in redirect_url.lower() or 'fcm' in redirect_url.lower():
                return False, "需要实名认证"
            
            # 进一步请求获取用户信息
            info_resp = requests.get(redirect_url, headers=HEADERS, timeout=10)
            try:
                # 尝试从响应中提取 realname_type 或其他标识
                # 这里简化判断，如果能正常跳转且不含 realname 关键词，通常认为已实名
                return True, "实名校验通过"
            except:
                return True, "实名校验通过(跳转成功)"
        else:
            return False, f"实名校验请求失败: HTTP {resp.status_code}"
    except Exception as e:
        return False, f"实名校验异常: {e}"


def do_login(username, password, ocr_engine, use_custom_model):
    """
    使用 OAuth 流程登录，并进行实名校验
    返回 (is_success, message)
    """
    session = requests.Session()
    session.headers.update(HEADERS)
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 1. 获取 OAuth 参数
            resp = session.get(OAUTH_URL, timeout=10)
            data = resp.json()
            init_url = data.get('result', '')
            if not init_url:
                log.warning(f'OAuth 参数获取失败: {data}')
                time.sleep(2)
                continue

            parsed = urlparse(init_url)
            qs = parse_qs(parsed.query)
            client_id = qs.get('client_id', [''])[0]
            state = qs.get('state', [''])[0]
            ref = qs.get('ref', [''])[0]
            if not (client_id and state and ref):
                log.warning('OAuth 参数缺失')
                time.sleep(2)
                continue

            # 2. 获取并识别验证码
            captcha_id = random_hex(48)
            captcha_text = ""
            try:
                img_resp = session.get(f"{CAPTCHA_URL}?captchaId={captcha_id}", timeout=10)
                if img_resp.status_code == 200:
                    captcha_text = recognize_captcha(img_resp.content, ocr_engine, use_custom_model)
            except Exception as e:
                log.debug(f'验证码获取失败: {e}')

            # 3. 执行登录
            login_params = {
                'isInputRealname': 'false',
                'isVaildRealname': 'false',
                'sec': '0',
                'captcha_id': captcha_id,
                'captcha': captcha_text,
                'password': password,
                'username': username,
                'client_id': client_id,
                'state': state,
                'ref': ref,
                'response_type': 'TOKEN',
                'scope': 'basic',
                'bizId': '2100001792',
                'auth_action': 'ORILOGIN',
                'redirect_uri': OAUTH_URL.split('?')[0] + '?' + OAUTH_URL.split('?')[1]
            }

            login_resp = session.post(
                OAUTH_LOGIN_URL,
                data=login_params,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                allow_redirects=False,
                timeout=10
            )

            # 4. 分析登录结果
            is_login_success = False
            if 300 <= login_resp.status_code < 400:
                redirect_url = login_resp.headers.get('location', '')
                if 'access_token=' in redirect_url:
                    is_login_success = True
                else:
                    log.warning(f'未知重定向: {redirect_url[:80]}')
            
            if not is_login_success:
                body = login_resp.text
                try:
                    result = json.loads(body)
                    code = result.get('code')
                    msg = result.get('message', '')
                    if code == '100':
                        is_login_success = True
                    elif code == '103':
                        return False, "需要二次验证(封号/风险)"
                    elif '验证码' in msg or 'captcha' in msg.lower():
                        log.info(f'验证码错误，重试...')
                        continue
                    else:
                        return False, f"code={code}, msg={msg}"
                except:
                    return False, f"响应不可解析: {body[:60]}"

            # 5. 实名校验 (保留)
            if is_login_success:
                verified, reason = check_realname(session)
                if not verified:
                    return False, f"登录成功但未实名: {reason}"
                return True, "登录成功且已实名"
            
            return False, "登录失败"

        except requests.RequestException as e:
            log.warning(f'网络错误: {e}')
            time.sleep(2)
            continue
        except Exception as e:
            log.error(f'未知错误: {e}')
            time.sleep(2)
            continue

    return False, "重试耗尽"
