#!/bin/bash

# Script to generate all required icon sizes from logo
# Requires ImageMagick: apt-get install imagemagick

INPUT="static/images/logo-original.png"
OUTPUT_DIR="static/images"

# Create output directory
mkdir -p $OUTPUT_DIR

# App Icons
convert $INPUT -resize 72x72 $OUTPUT_DIR/icon-72.png
convert $INPUT -resize 96x96 $OUTPUT_DIR/icon-96.png
convert $INPUT -resize 128x128 $OUTPUT_DIR/icon-128.png
convert $INPUT -resize 144x144 $OUTPUT_DIR/icon-144.png
convert $INPUT -resize 152x152 $OUTPUT_DIR/icon-152.png
convert $INPUT -resize 192x192 $OUTPUT_DIR/icon-192.png
convert $INPUT -resize 384x384 $OUTPUT_DIR/icon-384.png
convert $INPUT -resize 512x512 $OUTPUT_DIR/icon-512.png

# Favicons
convert $INPUT -resize 16x16 $OUTPUT_DIR/favicon-16x16.png
convert $INPUT -resize 32x32 $OUTPUT_DIR/favicon-32x32.png
convert $INPUT -resize 180x180 $OUTPUT_DIR/apple-touch-icon.png

# Notification badge (just the icon part, cropped)
convert $INPUT -resize 72x72 $OUTPUT_DIR/badge-72.png

echo "✅ All icons generated successfully!"
echo "Icons saved in $OUTPUT_DIR/"
