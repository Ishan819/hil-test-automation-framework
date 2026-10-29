#include "hil/protobuf_results.hpp"

#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

std::string read_file(const std::string& path) {
    std::ifstream stream(path, std::ios::binary | std::ios::ate);
    if (!stream) {
        throw std::runtime_error("Cannot open input file: " + path);
    }
    const auto size = stream.tellg();
    if (size < 0 || size > 16 * 1024 * 1024) {
        throw std::runtime_error("Input file is unreadable or exceeds 16 MiB");
    }
    std::string content(static_cast<std::size_t>(size), '\0');
    stream.seekg(0);
    stream.read(content.data(), static_cast<std::streamsize>(content.size()));
    if (!stream || stream.peek() != std::char_traits<char>::eof()) {
        throw std::runtime_error("Cannot read complete input file: " + path);
    }
    return content;
}

void write_new_file(const std::string& path, const std::string& content) {
    // Exclusive creation: this interoperability utility never replaces existing files.
    std::FILE* file = std::fopen(path.c_str(), "wbx");
    if (!file) {
        throw std::runtime_error("Cannot create output file (it may already exist): " + path);
    }
    const bool written = std::fwrite(content.data(), 1, content.size(), file) == content.size();
    const bool closed = std::fclose(file) == 0;
    if (!written || !closed) {
        std::filesystem::remove(path);
        throw std::runtime_error("Cannot write complete output file: " + path);
    }
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if ((argc == 4 || argc == 5) && std::string(argv[1]) == "produce") {
            const bool fault = argc == 5;
            if (fault && std::string(argv[4]) != "--fault") {
                throw std::invalid_argument("Expected --fault");
            }
            const hil::SimulatedBench bench(fault ? 0.0 : 5.0, fault ? 95.0 : 28.0, !fault);
            write_new_file(argv[2], hil::serialize_result(hil::bench_result(bench, argv[3])));
        } else if (argc == 3 && std::string(argv[1]) == "verify") {
            const auto result = hil::parse_result(read_file(argv[2]));
            std::cout << "run_id=" << result.run_id() << " cases=" << result.summary().total()
                      << " passed=" << result.summary().passed() << " failed=" << result.summary().failed()
                      << " skipped=" << result.summary().skipped() << '\n';
        } else if (argc == 4 && std::string(argv[1]) == "roundtrip") {
            const auto result = hil::parse_result(read_file(argv[2]));
            write_new_file(argv[3], hil::serialize_result(result));
        } else {
            throw std::invalid_argument(
                "Usage: hil_proto_exchange produce OUTPUT RUN_ID [--fault] | verify INPUT | roundtrip INPUT OUTPUT");
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << '\n';
        return 2;
    }
}
