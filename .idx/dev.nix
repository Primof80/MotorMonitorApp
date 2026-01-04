{ pkgs, ... }:
let
  # A custom Python environment with specified packages
  pythonWithPackages = pkgs.python311.withPackages (ps: with ps; [
    flask
    pandas
    plotly
    numpy
    pytest
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
          # The $PORT environment variable is automatically assigned
          command = ["flask" "run" "--host=0.0.0.0" "--port=$PORT"];
          manager = "web";
        };
      };
    };
  };
}
