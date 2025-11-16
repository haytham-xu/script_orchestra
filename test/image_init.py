import os
import shutil
from PIL import Image, ImageDraw, ImageFont

def delete_folder(folder: str):
    if os.path.exists(folder):
        shutil.rmtree(folder)

def generate_number_images(folder_path: str, image_number: int, border_thickness: int = 40):
    os.makedirs(folder_path, exist_ok=True)
    try:
        font = ImageFont.truetype("Arial.ttf", 120)
    except Exception:
        font = ImageFont.load_default()

    for i in range(image_number):
        text = str(i)
        img_w, img_h = 1080, 1920
        img = Image.new("RGBA", (img_w, img_h), (255, 255, 255, 255))  # 白色背景
        draw = ImageDraw.Draw(img)
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except AttributeError:
            try:
                bbox = font.getbbox(text)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            except Exception:
                tw, th = font.getsize(text)

        draw.text(((img_w - tw) / 2, (img_h - th) / 2), text, fill=(0, 0, 0), font=font)

        # 画粗黑色边框
        for offset in range(border_thickness):
            draw.rectangle(
                [offset, offset, img_w - 1 - offset, img_h - 1 - offset],
                outline=(0, 0, 0)
            )

        img.save(os.path.join(folder_path, f"{i}.png"))

root_path = "../test_data/sources/"

delete_folder(root_path)
generate_number_images(root_path + "[auth1]aaaaa[useless](ul_tag1)【ul_tag2】", 3)
generate_number_images(root_path + "[ccc][auth1]bbbbb", 6)
generate_number_images(root_path + "[auth2]ccccc", 9)
generate_number_images(root_path + "[auth3]ddddd", 5)
generate_number_images(root_path + "[auth4]eeeee", 2)
generate_number_images(root_path + "[auth4]akljsbf", 60)
generate_number_images(root_path + "[auth5]erba", 30)
generate_number_images(root_path + "[auth5]bkhbef", 30)
generate_number_images(root_path + "[auth5]zlidlhfn", 200)
generate_number_images(root_path + "[auth6]elknfa", 100)
generate_number_images(root_path + "[auth6]cljbef", 50)

generate_number_images(root_path + "[auth99]name01", 1)
generate_number_images(root_path + "[auth99]name02", 1)
generate_number_images(root_path + "[auth99]name03", 1)
generate_number_images(root_path + "[auth99]name04", 1)
generate_number_images(root_path + "[auth99]name05", 1)
generate_number_images(root_path + "[auth99]name06", 1)
generate_number_images(root_path + "[auth99]name07", 1)
generate_number_images(root_path + "[auth99]name08", 1)
generate_number_images(root_path + "[auth99]name09", 1)
generate_number_images(root_path + "[auth99]name10", 1)
generate_number_images(root_path + "[auth99]name11", 1)
generate_number_images(root_path + "[auth99]name12", 1)
generate_number_images(root_path + "[auth99]name13", 1)
generate_number_images(root_path + "[auth99]name14", 1)
generate_number_images(root_path + "[auth99]name15", 1)
generate_number_images(root_path + "[auth99]name16", 1)
generate_number_images(root_path + "[auth99]name17", 1)
generate_number_images(root_path + "[auth99]name18", 1)
generate_number_images(root_path + "[auth99]name19", 1)
generate_number_images(root_path + "[auth99]name20", 1)
