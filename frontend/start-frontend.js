#!/usr/bin/env node

const { execSync } = require('child_process');
const { existsSync, copyFileSync } = require('fs');
const { join } = require('path');

console.log('========================================');
console.log('Starting Frontend Development Server');
console.log('========================================');

const envLocalPath = join(__dirname, '.env.local');
const envExamplePath = join(__dirname, '.env.local.example');
const nodeModulesPath = join(__dirname, 'node_modules');

// Check if .env.local exists, if not copy from example
if (!existsSync(envLocalPath)) {
    console.log('Creating .env.local from .env.local.example...');
    copyFileSync(envExamplePath, envLocalPath);
}

// Install dependencies if node_modules doesn't exist
if (!existsSync(nodeModulesPath)) {
    console.log('Installing dependencies...');
    try {
        execSync('npm install', { stdio: 'inherit' });
    } catch (error) {
        console.error('Failed to install dependencies:', error);
        process.exit(1);
    }
}

// Start the development server
console.log('Starting Next.js development server on http://localhost:3000');
try {
    execSync('npm run dev', { stdio: 'inherit' });
} catch (error) {
    console.error('Failed to start development server:', error);
    process.exit(1);
}
