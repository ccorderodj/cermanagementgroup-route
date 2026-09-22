import MiniCssExtractPlugin from 'mini-css-extract-plugin';
import { BuildOptions } from '../types/config';

// const cssLoader = {
//     test: /\.css$/i,
//     include: paths.tailwind,
//     use: ['style-loader', 'css-loader', 'postcss-loader'],
// }
// export function buildCssLoader(options: BuildOptions) {
//     const { isDev, paths } = options;
//     return {
//         test: /\.css$/i,
//         include: paths.tailwind,
//         use: ['style-loader', 'css-loader', 'postcss-loader'],
//         exclude: /node_modules/,
//     }
// }

export function buildCssLoader(options: BuildOptions) {
    const { isDev, paths } = options;
    return {
        test: /\.s[ac]ss$/i,
        exclude: /node_modules/,
        include: paths.tailwind,
        use: [
            isDev ? 'style-loader' : MiniCssExtractPlugin.loader,
            {
                loader: 'css-loader',
                options: {
                    modules: {
                        auto: (resPath: string) => Boolean(resPath.includes('.module.')),
                        localIdentName: isDev
                            ? '[path][name]__[local]--[hash:base64:5]'
                            : '[hash:base64:8]',
                    },
                },
            },
            'postcss-loader',
            'sass-loader',
        ],
    };
}
