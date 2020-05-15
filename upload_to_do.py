import os

import boto


PHOTO_DIR = "/home/ed/dls/photos/"

def _user_creds():
    with open("docreds.rc") as ff:
        creds = ff.read()
    user_creds = {}
    for ln in creds.splitlines():
        if ln.startswith("spacekey"):
            user_creds["spacekey"] = ln.split("=")[-1].strip()
        elif ln.startswith("secret"):
            user_creds["secret"] = ln.split("=")[-1].strip()
        elif ln.startswith("bucket"):
            user_creds["bucket"] = ln.split("=")[-1].strip()
    return user_creds


def create_client():
    user_creds = _user_creds()
    conn = boto.connect_s3(aws_access_key_id=user_creds["spacekey"],
            aws_secret_access_key=user_creds["secret"],
            host="nyc3.digitaloceanspaces.com")
    bucket = conn.get_bucket(user_creds["bucket"])
    return bucket


def make_folder_public(folder):
    """By default DO makes everything private. Given a folder prefix, this
    makes all files beginning with that prefix public.
    """
    clt = create_client()
    keys = clt.get_all_keys(prefix=folder)
    for key in keys:
        key.make_public()


def main():
    import pudb
    pudb.set_trace()
    clt = create_client()
    for root, dirs, files in os.walk(PHOTO_DIR, topdown=True):
        container_name = os.path.basename(root)
        for photo_name in files:
            full_name = os.path.join(root, photo_name)
            remote_path = os.path.join(container_name, photo_name)
            remote_file = clt.new_key(remote_path)
            with open(full_name, "rb") as file_to_upload:
                remote_file.set_contents_from_file(file_to_upload)
            remote_file.set_acl("public-read")


if __name__ == "__main__":
    main()
