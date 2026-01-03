{ pkgs, ... }:
let
  # A custom Python environment with specified packages
  pythonWithPackages = pkgs.python311.withPackages (ps: with ps; [
    flask
    pandas
    plotly
    numpy
    pytest
    gunicorn # For production-ready hosting
  ]);
in
{
  # Nix packages to install
  packages = [
    pythonWithPackages
    pkgs.openssl # For SSL
    pkgs.firebase-tools
    pkgs.google-cloud-sdk # Added to get the full gcloud CLI
  ];

  # VS Code extensions to install
  idx = {
    extensions = [
      "ms-python.python"
    ];

    # Workspace lifecycle hooks
    workspace = {
      # Runs when a workspace is first created
      onCreate = {
        install-deps = "pip install -r requirements.txt";
      };
    };

    # Web previews
    previews = {
      enable = true;
      previews = {
        web = {
          # Command to start the web server for the preview
          # Gunicorn is a production-ready server that will run your Flask app
          # The $PORT environment variable is automatically assigned
          command = ["gunicorn" "--bind" "0.0.0.0:$PORT" "app:app"];
          manager = "web";
        };
      };
    };
  };
}
