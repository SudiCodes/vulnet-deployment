import subprocess

# Define the command you want to run
command = "snmptable -v 2c -c ismart -Cl -CB -Ci -OX -Cb -Cw 512 localhost ifTable"

# Run the command using subprocess
process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

# Read and print output in chunks
while True:
    chunk = process.stdout.read(1024)  # Adjust chunk size as needed
    if not chunk:
        break
    chunk = chunk.decode()
    print(chunk)

# Wait for the process to finish and capture any errors
stdout, stderr = process.communicate()

# Print any errors
if stderr:
    print("Error:", stderr.decode())
