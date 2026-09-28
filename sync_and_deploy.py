import os
import shutil
import zipfile
import urllib.request
import json

BASE_REPO = r"C:\Users\ipnes\.gemini\antigravity\brain\aa10b4a9-be7b-4665-b7cf-5a7b33b079e3\scratch\wolfhunt-tg"
EXT_SRC = r"C:\WOLFHUNT_CHROME_EXTENSION"
DESKTOP = r"C:\Users\ipnes\Desktop\Project\WolfHunter"
DOWNLOADS = r"D:\downloads"
GDRIVE = r"G:\Другие компьютеры\Мое устройство Компьютер\АЛЬФА\Project"

def make_zip(source_dir, output_zip):
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, source_dir)
                zf.write(abs_path, rel_path)
    print(f"Created zip: {output_zip} ({os.path.getsize(output_zip)} bytes)")

def sync():
    # 1. Package extension zip
    zip_desktop = os.path.join(DESKTOP, "WOLFHUNT_CHROME_EXTENSION.zip")
    make_zip(EXT_SRC, zip_desktop)

    # 2. Copy zip
    zip_repo = os.path.join(BASE_REPO, "WOLFHUNT_CHROME_EXTENSION.zip")
    zip_downloads = os.path.join(DOWNLOADS, "WOLFHUNT_CHROME_EXTENSION.zip")
    zip_gdrive = os.path.join(GDRIVE, "WOLFHUNT_CHROME_EXTENSION.zip")

    shutil.copy2(zip_desktop, zip_repo)
    shutil.copy2(zip_desktop, zip_downloads)
    if os.path.exists(GDRIVE):
        shutil.copy2(zip_desktop, zip_gdrive)
    print("Zip copied to repo, downloads, and gdrive.")

    # 3. Copy wolfhunt_tilda.html
    tilda_src = os.path.join(BASE_REPO, "wolfhunt_tilda.html")
    tilda_desktop = os.path.join(DESKTOP, "wolfhunt_tilda.html")
    tilda_downloads = os.path.join(DOWNLOADS, "wolfhunt_tilda.html")
    tilda_gdrive = os.path.join(GDRIVE, "wolfhunt_tilda.html")

    shutil.copy2(tilda_src, tilda_desktop)
    shutil.copy2(tilda_src, tilda_downloads)
    if os.path.exists(GDRIVE):
        shutil.copy2(tilda_src, tilda_gdrive)
    print("wolfhunt_tilda.html copied to desktop, downloads, and gdrive.")

    # 4. Copy main.py and ETALON_PROJECT_INFO.txt
    main_src = os.path.join(BASE_REPO, "main.py")
    shutil.copy2(main_src, os.path.join(DESKTOP, "main.py"))
    shutil.copy2(main_src, os.path.join(DESKTOP, "wolfhunt_render_main.py"))
    shutil.copy2(main_src, os.path.join(DOWNLOADS, "main.py"))
    if os.path.exists(GDRIVE):
        shutil.copy2(main_src, os.path.join(GDRIVE, "main.py"))
    
    info_src = os.path.join(BASE_REPO, "ETALON_PROJECT_INFO.txt")
    shutil.copy2(info_src, os.path.join(DESKTOP, "ETALON_PROJECT_INFO.txt"))
    shutil.copy2(info_src, os.path.join(DOWNLOADS, "ETALON_PROJECT_INFO.txt"))
    if os.path.exists(GDRIVE):
        shutil.copy2(info_src, os.path.join(GDRIVE, "ETALON_PROJECT_INFO.txt"))
    print("main.py and ETALON_PROJECT_INFO.txt copied.")

    # 5. Mirror unpacked extension
    for dest_dir in [
        os.path.join(DESKTOP, "WOLFHUNT_CHROME_EXTENSION"),
        os.path.join(DOWNLOADS, "WOLFHUNT_CHROME_EXTENSION"),
        os.path.join(GDRIVE, "WOLFHUNT_CHROME_EXTENSION")
    ]:
        if os.path.exists(os.path.dirname(dest_dir)):
            if os.path.exists(dest_dir):
                shutil.rmtree(dest_dir)
            shutil.copytree(EXT_SRC, dest_dir)
            print(f"Mirrored unpacked extension to: {dest_dir}")

    # 6. Trigger Render Deploy
    try:
        req = urllib.request.Request("https://api.render.com/deploy/srv-danv9q8473hc73as5u10?key=wLNT89LUQ7Y", data=b'', method='POST')
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            print(f"Render deploy triggered: {data.get('deploy', {}).get('id')}")
    except Exception as e:
        print(f"Render deploy trigger notice: {e}")

    # 7. Purge jsDelivr CDN
    for url in [
        "https://purge.jsdelivr.net/gh/snesterov/wolfhunt-tg@main/wolfhunt_tilda.html",
        "https://purge.jsdelivr.net/gh/snesterov/wolfhunt-tg@main/widget.js"
    ]:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                print(f"CDN purged: {url} ({r.status})")
        except Exception as e:
            print(f"CDN purge notice for {url}: {e}")

if __name__ == "__main__":
    sync()
