from io import BytesIO

from PIL import Image, ImageOps

from app.core.exceptions import BusinessError

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
_MAX_IMAGE_EDGE = 4096
_AVATAR_SIZE = (256, 256)


def normalize_avatar(content: bytes) -> bytes:
    if len(content) > MAX_UPLOAD_BYTES:
        raise BusinessError(413, "头像文件不能超过 2 MB")
    try:
        with Image.open(BytesIO(content), formats=["JPEG", "PNG", "WEBP"]) as source:
            if max(source.size) > _MAX_IMAGE_EDGE:
                raise BusinessError(422, "头像的宽和高不能超过 4096 像素")
            image = ImageOps.exif_transpose(source).convert("RGBA")
            square = ImageOps.fit(image, _AVATAR_SIZE, method=Image.Resampling.LANCZOS)
            output = BytesIO()
            square.save(output, "WEBP", quality=82)
            return output.getvalue()
    except (OSError, ValueError, EOFError, Image.DecompressionBombError) as exc:
        raise BusinessError(422, "请选择有效的 JPG、PNG 或 WebP 图片") from exc
