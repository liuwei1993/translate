#include "marian.h"

#include "onnxruntime_c_api.h"

namespace {

struct State {
    const OrtApi* api = nullptr;
    OrtEnv* env = nullptr;
    OrtMemoryInfo* memory = nullptr;
    OrtSession* encoder = nullptr;
    OrtSession* decoder = nullptr;
};

State g_state;

struct Value {
    const OrtApi* api = nullptr;
    OrtValue* value = nullptr;

    ~Value() {
        if (api != nullptr && value != nullptr) {
            api->ReleaseValue(value);
        }
    }
};

struct TypeInfo {
    const OrtApi* api = nullptr;
    OrtTensorTypeAndShapeInfo* info = nullptr;

    ~TypeInfo() {
        if (api != nullptr && info != nullptr) {
            api->ReleaseTensorTypeAndShapeInfo(info);
        }
    }
};

bool failed(const OrtApi* api, OrtStatus* status, std::string* error) {
    if (status == nullptr) {
        return false;
    }
    const char* message = api->GetErrorMessage(status);
    if (error != nullptr) {
        *error = message == nullptr ? "onnx runtime error" : message;
    }
    api->ReleaseStatus(status);
    return true;
}

void release_sessions() {
    if (g_state.api == nullptr) {
        return;
    }
    if (g_state.encoder != nullptr) {
        g_state.api->ReleaseSession(g_state.encoder);
        g_state.encoder = nullptr;
    }
    if (g_state.decoder != nullptr) {
        g_state.api->ReleaseSession(g_state.decoder);
        g_state.decoder = nullptr;
    }
}

bool make_tensor(const int64_t* data, size_t count, const int64_t* shape, size_t rank, ONNXTensorElementDataType type,
    Value* out, std::string* error) {
    return !failed(g_state.api,
        g_state.api->CreateTensorWithDataAsOrtValue(g_state.memory, const_cast<int64_t*>(data), count * sizeof(int64_t),
            shape, rank, type, &out->value),
        error);
}

bool make_float_tensor(float* data, size_t count, const int64_t* shape, size_t rank, Value* out, std::string* error) {
    out->api = g_state.api;
    return !failed(g_state.api,
        g_state.api->CreateTensorWithDataAsOrtValue(g_state.memory, data, count * sizeof(float), shape, rank,
            ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, &out->value),
        error);
}

bool tensor_dims(OrtValue* value, std::vector<int64_t>* dims, std::string* error) {
    TypeInfo info;
    info.api = g_state.api;
    if (failed(g_state.api, g_state.api->GetTensorTypeAndShape(value, &info.info), error)) {
        return false;
    }
    size_t rank = 0;
    if (failed(g_state.api, g_state.api->GetDimensionsCount(info.info, &rank), error)) {
        return false;
    }
    dims->assign(rank, 0);
    if (rank == 0) {
        return true;
    }
    return !failed(g_state.api, g_state.api->GetDimensions(info.info, dims->data(), rank), error);
}

int64_t argmax_row(const float* data, int64_t row, int64_t width) {
    const float* line = data + row * width;
    int64_t best = 0;
    float best_value = line[0];
    for (int64_t i = 1; i < width; ++i) {
        if (line[i] > best_value) {
            best_value = line[i];
            best = i;
        }
    }
    return best;
}

}  // namespace

bool mt_open(const std::string& encoder_path, const std::string& decoder_path, std::string* error) {
    if (g_state.api == nullptr) {
        const OrtApiBase* base = OrtGetApiBase();
        g_state.api = base->GetApi(ORT_API_VERSION);
        if (g_state.api == nullptr) {
            if (error != nullptr) {
                *error = "onnx runtime api 16 is unavailable";
            }
            return false;
        }
    }
    release_sessions();
    if (g_state.env == nullptr) {
        if (failed(g_state.api, g_state.api->CreateEnv(ORT_LOGGING_LEVEL_WARNING, "marian", &g_state.env), error)) {
            return false;
        }
    }
    if (g_state.memory == nullptr) {
        if (failed(g_state.api,
                g_state.api->CreateCpuMemoryInfo(OrtArenaAllocator, OrtMemTypeDefault, &g_state.memory), error)) {
            return false;
        }
    }
    OrtSessionOptions* options = nullptr;
    if (failed(g_state.api, g_state.api->CreateSessionOptions(&options), error)) {
        return false;
    }
    if (failed(g_state.api, g_state.api->SetIntraOpNumThreads(options, 2), error) ||
        failed(g_state.api, g_state.api->SetSessionGraphOptimizationLevel(options, ORT_ENABLE_EXTENDED), error)) {
        g_state.api->ReleaseSessionOptions(options);
        return false;
    }
    bool opened = !failed(g_state.api,
                       g_state.api->CreateSession(g_state.env, encoder_path.c_str(), options, &g_state.encoder), error) &&
                   !failed(g_state.api,
                       g_state.api->CreateSession(g_state.env, decoder_path.c_str(), options, &g_state.decoder), error);
    g_state.api->ReleaseSessionOptions(options);
    if (!opened) {
        release_sessions();
        return false;
    }
    return true;
}

void mt_close() {
    release_sessions();
}

bool mt_translate(const std::vector<int64_t>& input_ids, int64_t pad_id, int64_t eos_id, std::vector<int64_t>* output,
    std::string* error) {
    output->clear();
    if (g_state.encoder == nullptr || g_state.decoder == nullptr) {
        if (error != nullptr) {
            *error = "translation model is not open";
        }
        return false;
    }
    if (input_ids.empty()) {
        return true;
    }
    const int64_t sequence = static_cast<int64_t>(input_ids.size());
    const int64_t input_shape[2] = {1, sequence};
    std::vector<int64_t> mask(static_cast<size_t>(sequence), 1);
    Value input;
    Value mask_value;
    input.api = g_state.api;
    mask_value.api = g_state.api;
    if (!make_tensor(input_ids.data(), input_ids.size(), input_shape, 2, ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64, &input,
            error) ||
        !make_tensor(mask.data(), mask.size(), input_shape, 2, ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64, &mask_value,
            error)) {
        return false;
    }
    const char* encoder_names[] = {"input_ids", "attention_mask"};
    const OrtValue* encoder_inputs[] = {input.value, mask_value.value};
    const char* encoder_outputs_name[] = {"last_hidden_state"};
    Value encoded;
    encoded.api = g_state.api;
    if (failed(g_state.api,
            g_state.api->Run(g_state.encoder, nullptr, encoder_names, encoder_inputs, 2, encoder_outputs_name, 1,
                &encoded.value),
            error)) {
        return false;
    }
    std::vector<int64_t> hidden_dims;
    if (!tensor_dims(encoded.value, &hidden_dims, error) || hidden_dims.size() != 3) {
        if (error != nullptr && error->empty()) {
            *error = "encoder output rank is not 3";
        }
        return false;
    }
    size_t hidden_count = 1;
    for (int64_t dim : hidden_dims) {
        hidden_count *= static_cast<size_t>(dim);
    }
    float* hidden_data = nullptr;
    if (failed(g_state.api, g_state.api->GetTensorMutableData(encoded.value, reinterpret_cast<void**>(&hidden_data)),
            error)) {
        return false;
    }
    std::vector<float> hidden(hidden_data, hidden_data + hidden_count);
    const int64_t hidden_shape[3] = {hidden_dims[0], hidden_dims[1], hidden_dims[2]};

    std::vector<int64_t> generated;
    generated.reserve(65);
    generated.push_back(pad_id);
    for (int step = 0; step < 64; ++step) {
        int64_t best = 0;
        {
            const int64_t dec_len = static_cast<int64_t>(generated.size());
            const int64_t dec_shape[2] = {1, dec_len};
            Value dec_ids;
            Value dec_mask;
            Value hidden_value;
            dec_ids.api = g_state.api;
            dec_mask.api = g_state.api;
            if (!make_tensor(generated.data(), generated.size(), dec_shape, 2, ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64,
                    &dec_ids, error) ||
                !make_tensor(mask.data(), mask.size(), input_shape, 2, ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64, &dec_mask,
                    error) ||
                !make_float_tensor(hidden.data(), hidden.size(), hidden_shape, 3, &hidden_value, error)) {
                return false;
            }
            const char* decoder_names[] = {"input_ids", "encoder_attention_mask", "encoder_hidden_states"};
            const OrtValue* decoder_inputs[] = {dec_ids.value, dec_mask.value, hidden_value.value};
            const char* decoder_output_name[] = {"logits"};
            Value logits;
            logits.api = g_state.api;
            if (failed(g_state.api,
                    g_state.api->Run(g_state.decoder, nullptr, decoder_names, decoder_inputs, 3, decoder_output_name, 1,
                        &logits.value),
                    error)) {
                return false;
            }
            std::vector<int64_t> logit_dims;
            if (!tensor_dims(logits.value, &logit_dims, error) || logit_dims.size() < 2) {
                if (error != nullptr && error->empty()) {
                    *error = "decoder output rank is too small";
                }
                return false;
            }
            const int64_t width = logit_dims.back();
            const int64_t rows = logit_dims[logit_dims.size() - 2];
            if (width <= 0 || rows <= 0) {
                if (error != nullptr) {
                    *error = "decoder output is empty";
                }
                return false;
            }
            float* logit_data = nullptr;
            if (failed(g_state.api,
                    g_state.api->GetTensorMutableData(logits.value, reinterpret_cast<void**>(&logit_data)), error)) {
                return false;
            }
            best = argmax_row(logit_data, rows - 1, width);
        }
        if (best == eos_id) {
            break;
        }
        generated.push_back(best);
    }
    output->assign(generated.begin() + 1, generated.end());
    return true;
}
