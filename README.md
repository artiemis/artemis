### Virtual env setup
```
make venv
```

### Installing dependencies
```
make install
```

### Launching dev
```
make dev
```

### Launching dev + watch
```
make watch
```

### Launching prod
```
pm2 start
```

### Launching prod (manual)
```
. .venv/bin/activate
ENV=production python3 -m artemis.bot
```
