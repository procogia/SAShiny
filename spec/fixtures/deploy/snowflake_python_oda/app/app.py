import sashiny

app = sashiny.app(["cars.sashiny.yml"], sashiny.Pool(sashiny.connect_from_env, max_size=2))
