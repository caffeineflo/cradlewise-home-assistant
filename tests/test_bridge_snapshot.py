import numpy as np

from cradlewise_local.streamer import encode_jpeg


def test_encode_jpeg_returns_single_jpeg_image():
    image = np.zeros((16, 16, 3), dtype=np.uint8)
    image[:, :, 2] = 255

    jpeg = encode_jpeg(image)

    assert jpeg.startswith(b"\xff\xd8")
    assert jpeg.endswith(b"\xff\xd9")
