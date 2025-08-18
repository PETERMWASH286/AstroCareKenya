<?php
// Simple GitHub webhook endpoint
$secret = "edfgeh456uhsjkzx@#rws"; // optional for security

// Validate the GitHub payload (optional)
$headers = getallheaders();
$payload = file_get_contents('php://input');

// Execute deploy.sh safely
$output = shell_exec('./deploy.sh 2>&1');
echo "<pre>$output</pre>";
?>
