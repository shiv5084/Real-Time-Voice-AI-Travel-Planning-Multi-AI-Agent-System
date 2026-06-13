/** @type {import('jest').Config} */
module.exports = {
  testEnvironment: "jest-environment-jsdom",
  transform: {
    "^.+\\.(ts|tsx|js|jsx)$": ["babel-jest", { configFile: "./babel.config.js" }],
  },
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
    "\\.(css|less|scss|sass)$": "identity-obj-proxy",
    "\\.(jpg|jpeg|png|gif|svg|ico|webp)$": "<rootDir>/__mocks__/fileMock.js",
  },
  setupFilesAfterEnv: ["@testing-library/jest-dom"],
  testMatch: ["<rootDir>/src/__tests__/**/*.test.{ts,tsx,js}"],
  moduleFileExtensions: ["ts", "tsx", "js", "jsx", "json"],
};
