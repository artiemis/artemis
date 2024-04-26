module.exports = {
  apps: [
    {
      name: "artemis",
      script: "/bin/bash",
      args: "-c './env/bin/python -m artemis'",
      out_file: "/dev/null",
      error_file: "/dev/null",
      log_file: "./artemis.log",
      time: true,
      env: {
        PYTHONUNBUFFERED: "1",
        ENV: "production",
      },
    },
  ],
};
