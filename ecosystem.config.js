module.exports = {
  apps: [
    {
      name: "artemis",
      interpreter: "./env/bin/python",
      script: "./bot.py",
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
