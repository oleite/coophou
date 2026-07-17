#pragma once

#include <string>

bool compressString(const std::string &input, std::string &output);

namespace Color
{
    const std::string RESET = "\033[0m";
    const std::string SAGE = "\033[38;2;135;169;141m";  // Soft earth green
    const std::string ROSE = "\033[38;2;212;141;143m";  // Pastel dusty rose
    const std::string SLATE = "\033[38;2;112;128;144m"; // Cool muted blue-grey
    const std::string SAND = "\033[38;2;221;190;169m";  // Soft warm beige
}