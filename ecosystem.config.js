module.exports = {
  apps: [
    {
      name: "artemis",
      script: "./env/bin/python",
      args: "-m artemis.bot",
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
