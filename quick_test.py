import requests, time; time.sleep(45); print("Testing after deployment..."); r = requests.get("https://chroma-load-balancer.onrender.com/health"); print(f"Health: {r.status_code}")
