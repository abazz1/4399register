# onnx_recognizer.py
import os
import json
import numpy as np
import onnxruntime as ort
from PIL import Image
from io import BytesIO

class ONNXCaptchaRecognizer:
    def __init__(self, model_path: str, charset_path: str, captcha_len: int = 4):
        """
        model_path: ONNX 模型文件路径，如 'common.onnx'
        charset_path: 字符集 JSON 文件路径，如 'charset.json'
        captcha_len: 预期验证码长度，用于结果校验
        """
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"ONNX 模型不存在: {model_path}")
        if not os.path.exists(charset_path):
            raise FileNotFoundError(f"字符集文件不存在: {charset_path}")

        self.session = ort.InferenceSession(model_path)
        with open(charset_path, 'r', encoding='utf-8') as f:
            self.charset = json.load(f)
        self.captcha_len = captcha_len

    def recognize(self, img_bytes: bytes) -> str or None:
        """
        识别验证码图片，返回长度为 captcha_len 的字符串，失败返回 None
        """
        try:
            img = Image.open(BytesIO(img_bytes)).convert('L').resize((160, 64))
            arr = np.array(img, dtype=np.float32) / 255.0
            arr = (arr - 0.5) / 0.5
            inp = arr.reshape(1, 1, 64, 160)

            # ONNX 推理
            out = self.session.run(None, {'input': inp})[0]  # shape: [T, 1, num_classes]
            preds = np.argmax(out, axis=-1)  # [T, 1]

            # CTC 解码（去掉空白符和连续重复）
            result = []
            prev = -1
            for t in range(out.shape[0]):
                idx = preds[t, 0]
                if idx == 0:       # 空白符
                    prev = 0
                    continue
                if idx == prev:
                    continue
                if 0 < idx < len(self.charset):
                    result.append(self.charset[idx])
                prev = idx

            text = ''.join(result)
            if len(text) == self.captcha_len:
                return text
            return None
        except Exception:
            return None