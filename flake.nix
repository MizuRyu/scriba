{
  description = "scriba - local meeting recorder and transcriber for macOS";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
  };

  outputs =
    { self, nixpkgs }:
    let
      systems = [ "aarch64-darwin" "x86_64-darwin" ];
      eachSystem = nixpkgs.lib.genAttrs systems;
    in
    {
      # Python と依存は uv が管理する（uv.lock）。nix は周辺ツールだけを揃える。
      # BlackHole 2ch はドライバなので nix では入れない（brew install blackhole-2ch）。
      devShells = eachSystem (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          default = pkgs.mkShell {
            packages = [
              pkgs.uv
              pkgs.just
              pkgs.lefthook
              pkgs.gitleaks
              pkgs.ffmpeg
              pkgs.switchaudio-osx
              pkgs.zip
            ];

            shellHook = ''
              echo "scriba dev shell: just setup → just verify"
            '';
          };
        }
      );
    };
}
