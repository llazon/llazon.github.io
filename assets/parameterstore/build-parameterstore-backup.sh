# Create lambda zip file for parameterstore-backup.py

NAME="parameterstore-backup"
SOURCE_DIR="."
DEPLOYMENT_PACKAGE="${NAME}.zip"
FUNCTION="${NAME}.py"
PUBLIC_GPG="blah.gpg"
HANDLER="${NAME}.lambda_handler"

zip -j ../$DEPLOYMENT_PACKAGE $SOURCE_DIR/$FUNCTION
zip -j ../$DEPLOYMENT_PACKAGE $SOURCE_DIR/$PUBLIC_GPG

echo "Run manually to upload this package to S3:"
echo "aws s3 cp ../$DEPLOYMENT_PACKAGE s3://blah/$DEPLOYMENT_PACKAGE"
