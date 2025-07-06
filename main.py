import subprocess

# Lister les fichiers installés dans /usr/bin
files = subprocess.getoutput('ls /usr/bin')
print(f"Fichiers dans /usr/bin : {files}")