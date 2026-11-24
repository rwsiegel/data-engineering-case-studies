import resource, subprocess, sys
p = subprocess.run(sys.argv[1:], capture_output=True, text=True)
print(p.stdout[-600:], p.stderr[-300:])
print("peak_memory_mb", round(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024, 1), "exit", p.returncode)
