import { Config } from "@remotion/cli/config";

// Rendu WebGL des plans 3D dans le navigateur de rendu.
Config.setChromiumOpenGlRenderer("angle");
Config.setVideoImageFormat("jpeg");
Config.setJpegQuality(95);
Config.setCodec("h264");
Config.setCrf(16);
